from typing import Optional
import functools
import time
from ._mailbox_tasks import MailboxTasks
from . import _socket_context
from ..endpoint import Endpoint
import src.config


class MailboxSocketInterface(MailboxTasks):
    def socket_create(self) -> int:
        with self._mutex:
            sid = self._socket_allocate_id()
            self._sockets[sid] = _socket_context.Created()
            return sid

    def socket_close(self, sid: int):
        with self._mutex:
            if sid in self._sockets:
                context = self._sockets[sid]
                context.closed = True
                if isinstance(context, _socket_context.Waitable):
                    context: _socket_context.Waitable
                    with context.cv:
                        context.cv.notify_all()
                if isinstance(context, _socket_context.Connected):
                    context: _socket_context.Connected
                    del self._connected_sockets[(context.local_endpoint, context.remote_endpoint)]
                elif isinstance(context, _socket_context.Listening):
                    context: _socket_context.Listening
                    del self._listening_sockets[sid]
                del self._sockets[sid]

    def socket_connect(self, sid: int, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        with self._mutex:
            self._socket_check_status(sid, _socket_context.Created)
            if (local_endpoint, remote_endpoint) in self._connected_sockets:
                raise Exception('address already in use')
            self._connected_sockets[(local_endpoint, remote_endpoint)] = sid
            self._sockets[sid] = _socket_context.Connected(local_endpoint, remote_endpoint)

    def socket_listen(self, sid: int, local_endpoint: Endpoint):
        with self._mutex:
            self._socket_check_status(sid, _socket_context.Created)
            if any(local_endpoint.intersects_with(listening_endpoint)
                   for listening_endpoint in self._listening_sockets.values()):
                raise Exception('address already in use')
            self._listening_sockets[sid] = local_endpoint
            self._sockets[sid] = _socket_context.Listening(local_endpoint)

    def socket_accept(self, sid: int, timeout: Optional[float] = None) -> Optional[int]:
        context: _socket_context.Listening = self._socket_check_status(sid, _socket_context.Listening)
        with context.cv:
            while not context.queue and (timeout is None or timeout > 0):
                start = time.time()
                context.cv.wait(timeout)
                if timeout is not None:
                    timeout -= time.time() - start
            if not context.queue: # timeout
                return None
            sid = context.queue.popleft()
            conn_context: _socket_context.Connected = context.sockets[sid]
        with self._mutex:
            with context.cv:
                del context.connected_sockets[(conn_context.local_endpoint, conn_context.remote_endpoint)]
                del context.sockets[sid]
            self._sockets[sid] = conn_context
            self._connected_sockets[(conn_context.local_endpoint, conn_context.remote_endpoint)] = sid
            self._schedule_task(
                src.config.config['tom']['ATO'] / 1000,
                functools.partial(self._task_send_ack, sid, conn_context.next_seq))
            return sid

    def socket_send(self, sid: int, buf: bytes) -> int:
        context: _socket_context.Connected = self._socket_check_status(sid, _socket_context.Connected)
        with context.cv:
            seq = context.next_seq
            context.next_seq += 1
            context.pending_local[seq] = buf
            self._task_transmit(sid, seq)
        return len(buf)

    def socket_recv(self, sid: int, size: int, timeout: Optional[float] = None) -> Optional[bytes]:
        context: _socket_context.Connected = self._socket_check_status(sid, _socket_context.Connected)
        ret = b''
        with context.cv:
            while not context.closed and size > 0 and (timeout is None or timeout > 0):
                seq, off = context.recv_cursor
                payload = context.pending_remote.get(seq)
                if payload is not None:
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
                        timeout -= time.time() - start
        return ret
