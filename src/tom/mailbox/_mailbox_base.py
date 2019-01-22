from typing import Dict, Tuple, Type
import threading
from ._socket_context import SocketContext
from ..endpoint import Endpoint


class MailboxBase:
    _mutex: threading.RLock
    __next_socket_id = 0
    _sockets: Dict[int, SocketContext]
    _connected_sockets: Dict[Tuple[Endpoint, Endpoint], int]
    _listening_sockets: Dict[int, Endpoint]

    def __init__(self):
        self._mutex = threading.RLock()
        self._sockets = {}
        self._connected_sockets = {}
        self._listening_sockets = {}

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
