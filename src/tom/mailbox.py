from typing import Optional, Dict, Tuple, Callable, List, Any
import heapq
import functools
import email
import threading
import time
import smtplib
import imapclient
import imapclient.response_types
from . import Credential, Endpoint
from .socket_context import *
from .packet import Packet
from ..config import config


class Mailbox:
    __thread_listener: threading.Thread
    __thread_timer: threading.Thread
    __cv_timer: threading.Condition
    __mutex: threading.RLock
    # protected by mutex
    __next_socket_id = 0
    __sockets: Dict[int, SocketContext]
    __connected_sockets: Dict[Tuple[Endpoint, Endpoint], int]
    __transport: smtplib.SMTP
    # protected by __cv_timer
    __scheduled_tasks: List[Tuple[float, Callable]]
    __closed: bool = False
    # only used by __thread_listener
    __store: imapclient.IMAPClient
    __listener: imapclient.IMAPClient

    def __init__(self, smtp: Credential, imap: Credential):
        self.__sockets = {}
        self.__connected_sockets = {}
        self.__mutex = threading.RLock()

        self.__transport = self.__init_smtp(smtp)
        self.__store = self.__init_imap(imap)
        self.__listener = self.__init_imap(imap)

        self.__cv_timer = threading.Condition()
        self.__scheduled_tasks = []

        self.__thread_listener = threading.Thread(target=self.__listen)
        self.__thread_listener.start()

        self.__thread_timer = threading.Thread(target=self.__timer)
        self.__thread_timer.start()

    def __del__(self):
        self.close()

    def close(self):
        with self.__cv_timer:
            if self.__closed:
                return
            self.__closed = True
            self.__cv_timer.notifyAll()
        self.__transport.close()
        self.__store.logout()
        self.__listener.idle_done()
        self.__listener.logout()
        self.join()

    def join(self):
        self.__thread_listener.join()
        self.__thread_timer.join()

    def socket_create(self) -> int:
        with self.__mutex:
            sid = self.__next_socket_id
            self.__next_socket_id += 1
            self.__sockets[sid] = SocketContext()
            return sid

    def socket_close(self, sid: int):
        with self.__mutex:
            if sid in self.__sockets:
                context = self.__sockets[sid]
                context.closed = True
                if context.status == SocketStatus.CONNECTED:
                    context: SocketContextConnected
                    with context.cv:
                        context.cv.notifyAll()
                elif context.status == SocketStatus.LISTENING:
                    # TODO
                    pass
                del self.__sockets[sid]

    def socket_connect(self, sid: int, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        with self.__mutex:
            self.__socket_check_status(sid, SocketStatus.CREATED)
            if (local_endpoint, remote_endpoint) in self.__connected_sockets:
                raise Exception('address already in use')
            self.__connected_sockets[(local_endpoint, remote_endpoint)] = sid
            self.__sockets[sid] = SocketContextConnected(local_endpoint, remote_endpoint)

    def socket_listen(self, sid: int, local_endpoint: Endpoint):
        # TODO
        pass

    def socket_accept(self, sid: int, timeout: Optional[float]) -> int:
        # TODO
        pass

    def socket_send(self, sid: int, buf: bytes) -> int:
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        with context.cv:
            seq = context.next_seq
            context.next_seq += 1
            context.pending_local[seq] = buf
            self.__task_transmit(sid, seq)
        return len(buf)

    def socket_recv(self, sid: int, size: int, timeout: Optional[float] = None) -> Optional[bytes]:
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        ret = b''
        with context.cv:
            while not context.closed and size > 0 and (timeout is None or timeout > 0):
                seq, off = context.recv_cursor
                payload = context.pending_remote.get(seq)
                if not payload is None:
                    seg = payload[off:off + size]
                    ret += seg
                    size -= len(seg)
                    if off + len(seg) >= len(payload):
                        context.recv_cursor = (seq + 1, 0)
                        del context.pending_remote[seq]
                    else:
                        context.recv_cursor = (seq, off + len(seg))
                else:
                    start = time.time()
                    context.cv.wait(timeout)
                    if not timeout is None:
                        timeout -= (time.time() - start)
        return ret

    def __socket_check_status(self, sid: int, status: SocketStatus) -> SocketContext:
        with self.__mutex:
            if not sid in self.__sockets:
                raise Exception('socket does not exist')
            context = self.__sockets[sid]
            if context.status != status:
                raise Exception('invalid status of socket: expected "{}", got "{}"'
                                .format(status, context.status))
            return context

    @staticmethod
    def __init_smtp(credential: Credential) -> smtplib.SMTP:
        smtp = smtplib.SMTP(credential.host, credential.port)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(credential.username, credential.password)
        return smtp

    @staticmethod
    def __init_imap(credential: Credential) -> imapclient.IMAPClient:
        imap = imapclient.IMAPClient(credential.host, credential.port, ssl=True, use_uid=True)
        imap.login(credential.username, credential.password)
        imap.select_folder('INBOX')
        return imap

    def __listen(self):
        self.__listener.idle()
        self.__check_new_packets()
        while True:
            try:
                responses = self.__listener.idle_check()
            except OSError:
                # disconnected from IMAP
                return
            if any(response[1] == b'EXISTS' for response in responses):
                self.__check_new_packets()

    def __check_new_packets(self):
        uids = self.__store.search('UNSEEN')
        messages = self.__store.fetch(uids, ['ENVELOPE', 'BODY.PEEK[]'])
        seens = []
        for uid, message in messages.items():
            try:
                if self.__process_incoming_packet(message):
                    seens.append(uid)
            except Exception as e:
                # ignore invalid packets
                pass
        if seens:
            self.__store.add_flags(seens, [imapclient.SEEN])

    def __process_incoming_packet(self, message: Dict[bytes, Any]) -> bool:
        msg = email.message_from_bytes(message[b'BODY[]'])
        envelope: imapclient.response_types.Envelope = message[b'ENVELOPE']
        if envelope.sender[0].mailbox != envelope.from_[0].mailbox:
            raise Exception('invalid packet: inconsistenct sender and from header')
        packet = Packet.from_message(msg)
        remote_endpoint = Endpoint(envelope.from_[0].mailbox, envelope.from_[0].name)

        seen: bool = False
        with self.__mutex:
            for to in envelope.to:
                local_endpoint = Endpoint(to.mailbox, to.name)
                sid = self.__connected_sockets.get((local_endpoint, remote_endpoint))
                if sid is None:
                    continue
                context: SocketContextConnected = self.__sockets[sid]
                with context.cv:
                    for ack_seq, ack_attempt in packet.acks:
                        self.__process_ack(sid, ack_seq, ack_attempt)
                    if packet.seq != -1: # no action for pure ack
                        context.pending_remote[packet.seq] = packet.payload
                        context.to_ack.add((packet.seq, packet.attempt))
                        self.__schedule_task(
                            config['tom']['ATO'] / 1000,
                            functools.partial(self.__task_send_ack, sid, context.next_seq))
                        context.cv.notifyAll()
                seen = True

        return seen

    def __process_ack(self, sid: int, seq: int, attempt: int):
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        total_attempts = context.attempts.get(seq)
        if total_attempts is None:
            # duplicated ack
            return
        del context.pending_local[seq]
        context.to_ack -= context.sent_acks[(seq, attempt)]
        for i in range(total_attempts):
            del context.sent_acks[(seq, i)]
        del context.attempts[seq]

    def __timer(self):
        with self.__cv_timer:
            while not self.__closed:
                if self.__scheduled_tasks:
                    scheduled_time, task = self.__scheduled_tasks[0]
                    now = time.time()
                    if scheduled_time <= now:
                        heapq.heappop(self.__scheduled_tasks)
                        try:
                            task()
                        except Exception:
                            # TODO: exception handling for scheduled tasks
                            pass
                    else:
                        self.__cv_timer.wait(scheduled_time - now)
                else:
                    self.__cv_timer.wait()

    def __schedule_task(self, delay: float, task: Callable):
        with self.__cv_timer:
            heapq.heappush(self.__scheduled_tasks, (time.time() + delay, task))
            self.__cv_timer.notifyAll()

    def __task_transmit(self, sid: int, seq: int):
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        with context.cv:
            acks = set(context.to_ack)
            local_endpoint, remote_endpoint = context.local_endpoint, context.remote_endpoint
            if seq == -1:
                packet = Packet(context.local_endpoint, context.remote_endpoint, seq, 0, acks, b'')
            elif not seq in context.pending_local:
                # already acked
                return
            else:
                attempt = context.attempts[seq]
                context.attempts[seq] += 1
                context.sent_acks[(seq, attempt)] = acks
                packet = Packet(
                    context.local_endpoint,
                    context.remote_endpoint, seq,
                    attempt, acks,
                    context.pending_local[seq])
        msg = packet.to_message()
        with self.__mutex:
            self.__transport.sendmail(local_endpoint.address, remote_endpoint.address, msg.as_bytes())
        if seq != -1: # do not retransmit pure acks
            self.__schedule_task(config['tom']['RTO'] / 1000, functools.partial(self.__task_transmit, sid, seq))

    def __task_send_ack(self, sid: int, next_seq: int):
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        with context.cv:
            if context.next_seq != next_seq:
                # another packet carrying ack has been sent
                return
        # pure ack does not consume seq number
        self.__task_transmit(sid, -1)
