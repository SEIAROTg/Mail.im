from typing import Dict, Any, Tuple, Optional
import contextlib
import email
import os
import threading
import imapclient.response_types
from .mailbox_tasks import MailboxTasks
from .packet import Packet, PlainPacket, SecurePacket
from ..credential import Credential
from . import socket_context, imapclient


class MailboxListener(MailboxTasks):
    __store: imapclient.IMAPClient
    __listener: imapclient.IMAPClient
    __mutex_listener: threading.RLock
    __selfpipe: Tuple[int, int]
    __thread_listener: threading.Thread
    __closed: bool = False

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
        self.__mutex_listener = threading.RLock()
        self.__selfpipe = os.pipe()
        self.__thread_listener = threading.Thread(target=self.__listen)
        self.__thread_listener.start()

    def join(self):
        super().join()
        self.__thread_listener.join()

    def close(self):
        with self._mutex:
            if self.__closed:
                return
            self.__closed = True
        super().close()
        os.close(self.__selfpipe[1])
        with self.__mutex_listener:
            self.__store.logout()
            self.__listener.logout()
        self.join()

    def __listen(self):
        with self.__mutex_listener:
            self.__listener.idle()
            self.__check_new_packets()
            while True:
                responses = self.__listener.idle_check(selfpipe=self.__selfpipe[0])
                if responses is None:  # selfpipe triggered
                    self.__listener.idle_done()
                    return
                if any(response[1] == b'EXISTS' for response in responses):
                    self.__check_new_packets()
            # TODO: handle exception

    def __check_new_packets(self):
        self.__store.noop()
        uids = self.__store.search('UNSEEN')
        messages = self.__store.fetch(uids, ['BODY.PEEK[]'])
        seens = []
        for uid, message in messages.items():
            if self.__try_process_packet(message):
                seens.append(uid)
        if seens:
            self.__store.add_flags(seens, [imapclient.SEEN])

    def _process_packet_connected(self, sid: int, context: socket_context.Connected, packet: Packet):
        secure = isinstance(context, socket_context.SecureConnected)
        with context.cv:
            if secure:
                packet: SecurePacket
                context: socket_context.SecureConnected
                packet = packet.decrypt(context.ratchet, context.xeddsa)
            packet: PlainPacket
            for ack_seq, ack_attempt in packet.acks:
                self.__process_ack(context, ack_seq, ack_attempt)
            if packet.seq != -1 and packet.seq >= context.recv_cursor[0]:
                # no action for pure ack and duplicated packets
                context.pending_remote[packet.seq] = packet.payload
                context.to_ack.add((packet.seq, packet.attempt))
                self._schedule_ack(sid, context)

                seq, off = context.recv_cursor
                while context.pending_remote.get(seq) == b'':
                    del context.pending_remote[seq]
                    seq += 1
                    off = 0
                context.recv_cursor = seq, off
                if context.pending_remote.get(seq):
                    self._socket_update_ready_status(sid, 'read', True)
                elif secure and packet.seq == 0:  # handshake response
                    del context.attempts[0]
                    del context.pending_local[0]
                context.syn_seq = None
                context.cv.notify_all()
        return True

    def __try_process_packet_connected(self, packet: Packet, secure: bool) -> bool:
        with self._mutex:
            sid = self._connected_sockets.get((packet.to, packet.from_))
            try:
                context: socket_context.Connected = self._socket_check_status(sid, socket_context.Connected)
            except Exception:
                return False
            if secure != isinstance(context, socket_context.SecureConnected):
                return False
            return self._process_packet_connected(sid, context, packet)

    def __try_process_packet_listening(self, packet: Packet, secure: bool) -> bool:
        with self._mutex:
            sid = next((sid
                        for sid, listening_endpoint in self._listening_sockets.items()
                        if listening_endpoint.matches(packet.to)), None)
            try:
                context: socket_context.Listening = self._socket_check_status(sid, socket_context.Listening)
            except Exception:
                return False
            with context.cv:
                conn_sid = context.connected_sockets.get((packet.to, packet.from_))
                if conn_sid is not None:  # existing pending connection
                    conn_context = context.sockets[conn_sid]
                    if secure != isinstance(conn_context, socket_context.SecureConnected):
                        return False
                    conn_context.pending_packets.append(packet)
                elif packet.is_syn:  # new connection
                    conn_sid = self._socket_allocate_id()
                    context.queue.append(conn_sid)
                    context.connected_sockets[(packet.to, packet.from_)] = conn_sid
                    self._socket_update_ready_status(sid, 'read', True)
                    context.cv.notify_all()
                    if secure:
                        packet: SecurePacket
                        conn_context = socket_context.SecureConnected(
                            packet.to,
                            packet.from_)
                    else:
                        conn_context = socket_context.Connected(
                            packet.to,
                            packet.from_)
                    conn_context.pending_packets.append(packet)
                    context.sockets[conn_sid] = conn_context
                else:
                    return False
            return True

    @staticmethod
    def __try_parse_packet(msg: email.message.Message) -> Optional[Tuple[Packet, bool]]:
        with contextlib.suppress(Exception):
            return PlainPacket.from_message(msg), False
        with contextlib.suppress(Exception):
            return SecurePacket.from_message(msg), True
        return None

    def __try_process_packet(self, message: Dict[bytes, Any]) -> bool:
        msg = email.message_from_bytes(message[b'BODY[]'])
        ret = self.__try_parse_packet(msg)
        return ret and bool(self.__try_process_packet_connected(*ret) or self.__try_process_packet_listening(*ret))
        # TODO: check the seq range of packet
        # TODO: check if duplicated attempts of a packet are same

    def __process_ack(self, context: socket_context.Connected, seq: int, attempt: int):
        total_attempts = context.attempts.get(seq)
        if total_attempts is None:
            # duplicated ack
            return
        del context.pending_local[seq]
        context.to_ack -= context.sent_acks[(seq, attempt)]
        for i in range(total_attempts):
            del context.sent_acks[(seq, i)]
        del context.attempts[seq]
