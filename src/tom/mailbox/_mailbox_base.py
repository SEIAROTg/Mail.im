from typing import Dict, Tuple, Type
import threading
from ._socket_context import SocketContext
from . import _socket_context
from ..endpoint import Endpoint
from ._epoll_context import EpollContext


class MailboxBase:
    _mutex: threading.RLock
    __next_socket_id = 0
    _sockets: Dict[int, SocketContext]
    _connected_sockets: Dict[Tuple[Endpoint, Endpoint], int]
    _listening_sockets: Dict[int, Endpoint]

    _next_epoll_id = 0
    _epolls: Dict[int, EpollContext]

    def __init__(self):
        self._mutex = threading.RLock()
        self._sockets = {}
        self._connected_sockets = {}
        self._listening_sockets = {}
        self._epolls = {}

    def _socket_check_status(self, sid: int, status: Type[SocketContext]) -> SocketContext:
        with self._mutex:
            if not sid in self._sockets:
                raise Exception('socket does not exist')
            context = self._sockets[sid]
            if not isinstance(context, status):
                raise Exception('invalid status of socket')
            return context

    def _socket_allocate_id(self) -> int:
        with self._mutex:
            sid = self.__next_socket_id
            self.__next_socket_id += 1
            return sid

    def _socket_update_ready_status(self, sid: int, type_: str, ready: bool):
        with self._mutex:
            context: _socket_context.Epollable = self._socket_check_status(sid, _socket_context.Epollable)
            with context.mutex:
                if type_ == 'read':
                    eids = context.repolls
                elif type_ == 'error':
                    eids = context.xepolls
                else:
                    assert False
            for eid in eids:
                epoll_context = self._epolls[eid]
                with epoll_context.cv:
                    if type_ == 'read':
                        rs = epoll_context.rrset
                    elif type_ == 'error':
                        rs = epoll_context.rxset
                    else:
                        assert False
                    if ready:
                        rs.add(sid)
                        epoll_context.cv.notifyAll()
                    else:
                        rs.remove(sid)
