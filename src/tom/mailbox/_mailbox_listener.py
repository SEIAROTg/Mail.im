from typing import Dict, Any
import functools
import email
import threading
import imapclient
import imapclient.response_types
from ._mailbox_tasks import MailboxTasks
from ._packet import Packet
from ..endpoint import Endpoint
from ..credential import Credential
from . import _socket_context
import src.config


class MailboxListener(MailboxTasks):
    __store: imapclient.IMAPClient
    __listener: imapclient.IMAPClient
    __thread_listener: threading.Thread

    @staticmethod
    def __init_imap(credential: Credential) -> imapclient.IMAPClient:
        imap = imapclient.IMAPClient(credential.host, credential.port, ssl=True, use_uid=True)
        imap.login(credential.username, credential.password)
        imap.select_folder('INBOX')
        return imap

    def __init__(self, imap: Credential, **kwargs):
        super().__init__(**kwargs)
        self.__store = self.__init_imap(imap)
        self.__listener = self.__init_imap(imap)
        self.__thread_listener = threading.Thread(target=self.__listen)
        self.__thread_listener.start()

    def join(self):
        super().join()
        self.__thread_listener.join()

    def close(self):
        super().close()
        self.__store.logout()
        self.__listener.idle_done()
        self.__listener.logout()
        self.join()

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
            raise Exception('invalid packet: inconsistent sender and from header')
        packet = Packet.from_message(msg)
        remote_endpoint = Endpoint(envelope.from_[0].mailbox, envelope.from_[0].name)

        seen: bool = False
        with self._mutex:
            for to in envelope.to:
                local_endpoint = Endpoint(to.mailbox, to.name)
                sid = self._connected_sockets.get((local_endpoint, remote_endpoint))
                if sid is not None:  # connected socket
                    context: _socket_context.Connected = self._sockets[sid]
                    with context.cv:
                        for ack_seq, ack_attempt in packet.acks:
                            self.__process_ack(sid, ack_seq, ack_attempt)
                        if packet.seq != -1:  # no action for pure ack
                            context.pending_remote[packet.seq] = packet.payload
                            context.to_ack.add((packet.seq, packet.attempt))
                            self._schedule_task(
                                src.config.config['tom']['ATO'] / 1000,
                                functools.partial(self._task_send_ack, sid, context.next_seq))
                            if packet.payload and packet.seq == context.recv_cursor[0]:
                                self._socket_update_ready_status(sid, 'read', True)
                            context.cv.notify_all()
                    seen = True
                    continue

                sid = next((sid
                            for sid, listening_endpoint in self._listening_sockets.items()
                            if listening_endpoint.matches(local_endpoint)), None)
                if sid is not None:  # listening socket
                    context: _socket_context.Listening = self._sockets[sid]
                    with context.cv:
                        conn_sid = context.connected_sockets.get((local_endpoint, remote_endpoint))
                        if conn_sid: # existing pending connection
                            conn_context = context.sockets[sid]
                        else:  # new pending connection
                            conn_sid = self._socket_allocate_id()
                            conn_context = _socket_context.Connected(local_endpoint, remote_endpoint)
                            context.sockets[conn_sid] = conn_context
                            context.connected_sockets[(local_endpoint, remote_endpoint)] = conn_sid
                            context.queue.append(conn_sid)
                            self._socket_update_ready_status(sid, 'read', True)
                            context.cv.notify_all()
                        conn_context.pending_remote[packet.seq] = packet.payload
                        conn_context.to_ack.add((packet.seq, packet.attempt))
                    seen = True
                    continue
        return seen

    def __process_ack(self, sid: int, seq: int, attempt: int):
        context: _socket_context.Connected = self._socket_check_status(sid, _socket_context.Connected)
        total_attempts = context.attempts.get(seq)
        if total_attempts is None:
            # duplicated ack
            return
        del context.pending_local[seq]
        context.to_ack -= context.sent_acks[(seq, attempt)]
        for i in range(total_attempts):
            del context.sent_acks[(seq, i)]
        del context.attempts[seq]
