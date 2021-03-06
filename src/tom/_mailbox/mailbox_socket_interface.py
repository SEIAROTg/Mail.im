from typing import Optional, Callable, Union, Tuple
import functools
import time
import pickle
import doubleratchet.header
from .mailbox_listener import MailboxListener
from . import socket_context
from ..endpoint import Endpoint
from .packet import SecurePacket, PlainPacket


class MailboxSocketInterface(MailboxListener):
    def socket_create(self) -> int:
        with self._mutex:
            sid = self._socket_allocate_id()
            self._sockets[sid] = socket_context.Created()
            return sid

    def socket_shutdown(self, sid: int):
        self._socket_shutdown(sid)

    def socket_close(self, sid: int):
        with self._mutex:
            if self._sockets.get(sid):
                self._socket_shutdown(sid)
                self._sockets.pop(sid, None)

    def socket_connect(
            self,
            sid: int,
            local_endpoint: Endpoint,
            remote_endpoint: Endpoint,
            sign_key_pair: Optional[Tuple[bytes, bytes]] = None,
            timeout: Optional[float] = None):
        with self._mutex:
            self._socket_check_status(sid, socket_context.Created)
            if (local_endpoint, remote_endpoint) in self._connected_sockets:
                raise Exception('address already in use')
            self._connected_sockets[(local_endpoint, remote_endpoint)] = sid
            if sign_key_pair is not None:
                context = socket_context.SecureConnected(local_endpoint, remote_endpoint, *sign_key_pair)
                context.next_seq = 1
                context.pending_local[0] = SecurePacket.encrypt(
                    PlainPacket(context.local_endpoint, context.remote_endpoint, 0, 0, set(), b'', is_syn=True),
                    context.ratchet,
                    context.xeddsa)
            else:
                context = socket_context.Connected(local_endpoint, remote_endpoint)
                context.syn_seq = 0
            self._sockets[sid] = context
        if sign_key_pair is not None:
            ok = True
            with context.cv:
                self._task_transmit(sid, context, 0)
                while 0 in context.pending_local and (timeout is None or timeout > 0):
                    start = time.time()
                    context.cv.wait(timeout)
                    if timeout is not None:
                        timeout -= start
                if 0 in context.pending_local:  # handshake timeout
                    ok = False
                else:
                    context.handshaked = True
            if not ok:
                self._socket_shutdown(sid)
                raise Exception('unable to connect: handshake timeout')

    def socket_listen(self, sid: int, local_endpoint: Endpoint):
        with self._mutex:
            self._socket_check_status(sid, socket_context.Created)
            if any(local_endpoint.intersects_with(listening_endpoint)
                   for listening_endpoint in self._listening_sockets.values()):
                raise Exception('address already in use')
            self._listening_sockets[sid] = local_endpoint
            self._sockets[sid] = socket_context.Listening(local_endpoint)

    def socket_accept(
            self,
            sid: int,
            should_accept: Optional[Callable[[Endpoint, Endpoint, bool], Union[bool, bytes]]] = None,
            timeout: Optional[float] = None
    ) -> Optional[int]:
        context: socket_context.Listening = self._socket_check_status(sid, socket_context.Listening)
        with context.cv:
            while True:
                decision = False
                while decision == False:
                    while not context.closed and not context.queue and (timeout is None or timeout > 0):
                        start = time.time()
                        context.cv.wait(timeout)
                        if timeout is not None:
                            timeout -= time.time() - start
                    if context.closed:
                        raise Exception('socket already closed')
                    if not context.queue: # timeout
                        return None
                    conn_sid = context.queue.popleft()
                    conn_context: socket_context.Connected = context.sockets[conn_sid]
                    del context.connected_sockets[(conn_context.local_endpoint, conn_context.remote_endpoint)]
                    del context.sockets[conn_sid]
                    secure = isinstance(conn_context, socket_context.SecureConnected)
                    decision = should_accept is None \
                        or should_accept(conn_context.local_endpoint, conn_context.remote_endpoint, secure)
                if secure and type(decision) == tuple:  # new secure connection
                    conn_context: socket_context.SecureConnected
                    dh_pub = conn_context.pending_packets[0].dr_header.dh_pub
                    for packet in conn_context.pending_packets:
                        if not packet.is_syn or packet.body or packet.dr_header.dh_pub != dh_pub:
                            continue
                    conn_context: socket_context.SecureConnected = socket_context.SecureConnected(
                        conn_context.local_endpoint,
                        conn_context.remote_endpoint,
                        decision[0],
                        decision[1],
                        None,
                        dh_pub)
                    packet = PlainPacket(conn_context.local_endpoint, conn_context.remote_endpoint, 0, 0, set(), b'')
                    packet = SecurePacket.encrypt(packet, conn_context.ratchet, conn_context.xeddsa)
                    conn_context.next_seq = 1
                    conn_context.recv_cursor = 1, 0
                    conn_context.pending_local[0] = packet
                elif secure and type(decision) != bytes:
                    continue
                else:  # plain or restore connection
                    pending_packets = conn_context.pending_packets
                    if decision == True:
                        conn_context = socket_context.Connected(conn_context.local_endpoint, conn_context.remote_endpoint)
                    else:
                        old_conn_context = conn_context
                        conn_context = pickle.loads(decision)
                        if secure != isinstance(conn_context, socket_context.SecureConnected):
                            continue
                        conn_context.local_endpoint = old_conn_context.local_endpoint
                        conn_context.remote_endpoint = old_conn_context.remote_endpoint
                    context.cv.release()
                    for packet in pending_packets:
                        self._process_packet_connected(sid, conn_context, packet)
                    context.cv.acquire()
                conn_context.syn_seq = None
                if secure:
                    conn_context.handshaked = True
                break
        with self._mutex:
            with context.cv:
                if not context.queue:
                    self._socket_update_ready_status(sid, 'read', False)
            self._sockets[conn_sid] = conn_context
            self._connected_sockets[(conn_context.local_endpoint, conn_context.remote_endpoint)] = conn_sid
            if conn_context.pending_local:
                for seq in conn_context.pending_local:
                    self._schedule_task(0, functools.partial(self._task_transmit, conn_sid, conn_context, seq))
            elif conn_context.to_ack:
                self._schedule_ack(conn_sid, conn_context)
            return conn_sid

    def socket_send(self, sid: int, buf: bytes) -> int:
        context: socket_context.Connected = self._socket_check_status(sid, socket_context.Connected)
        with context.cv:
            if context.closed:
                raise Exception('socket already closed')
            seq = context.next_seq
            context.next_seq += 1
            packet = PlainPacket(
                context.local_endpoint,
                context.remote_endpoint,
                seq,
                0,
                set(context.to_ack),
                buf,
                is_syn=seq == context.syn_seq)
            if isinstance(context, socket_context.SecureConnected):
                if not context.handshaked:
                    raise Exception('unable to send data before handshake')
                packet = SecurePacket.encrypt(packet, context.ratchet, context.xeddsa)
            context.pending_local[seq] = packet
        self._task_transmit(sid, context, seq)
        return len(buf)

    def socket_recv(self, sid: int, max_size: int, timeout: Optional[float] = None) -> bytes:
        context: socket_context.Connected = self._socket_check_status(sid, socket_context.Connected)
        with context.cv:
            while (
                    not context.closed
                    and not context.pending_remote.get(context.recv_cursor[0])
                    and (timeout is None or timeout > 0)):
                start = time.time()
                context.cv.wait(timeout)
                if timeout:
                    timeout -= time.time() - start
            seq, off = context.recv_cursor
            ret = b''
            payload = context.pending_remote.get(seq)
            while payload is not None and max_size:
                seg = payload[off:off+max_size]
                ret += seg
                max_size -= len(seg)
                off += len(seg)
                if off >= len(payload):
                    del context.pending_remote[seq]
                    seq += 1
                    off = 0
                payload = context.pending_remote.get(seq)
            while payload == b'':
                seq += 1
                payload = context.pending_remote.get(seq)
            context.recv_cursor = (seq, off)
            if context.closed and not ret:
                raise Exception('socket already closed')
            if payload is None:
                self._socket_update_ready_status(sid, 'read', False)
            return ret

    def socket_dump(self, sid: int) -> bytes:
        context: socket_context.Connected = self._socket_check_status(sid, socket_context.Connected)
        with context.cv:
            return pickle.dumps(context)

    def socket_restore(self, dump: bytes) -> int:
        context: socket_context.Connected = pickle.loads(dump)
        if not isinstance(context, socket_context.Connected):
            raise Exception('invalid socket dump: socket not connected')
        with self._mutex:
            sid = self._socket_allocate_id()
            if (context.local_endpoint, context.remote_endpoint) in self._connected_sockets:
                raise Exception('address already in use')
            self._connected_sockets[(context.local_endpoint, context.remote_endpoint)] = sid
            self._sockets[sid] = context
            if context.pending_local:
                for seq in context.pending_local:
                    self._schedule_task(0, functools.partial(self._task_transmit, sid, context, seq))
            elif context.to_ack:
                self._schedule_ack(sid, context)
        return sid

    def socket_endpoints(self, sid: int) -> Tuple[Optional[Endpoint], Optional[Endpoint]]:
        context = self._socket_check_status(sid, socket_context.SocketContext)
        if isinstance(context, socket_context.Connected):
            return context.local_endpoint, context.remote_endpoint
        if isinstance(context, socket_context.Listening):
            return context.local_endpoint, None
        return None, None
