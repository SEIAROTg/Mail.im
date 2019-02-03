from __future__ import annotations
import time
from typing import Optional, List, Tuple
from . import Mailbox, Endpoint


class Socket:
    __id: int = -1
    __mailbox: Mailbox

    def __init__(self, mailbox: Mailbox, id: Optional[int] = None):
        self.__mailbox = mailbox
        if id is None:
            self.__id = mailbox.socket_create()
        else:
            self.__id = id

    def __eq__(self, other: Socket) -> bool:
        return self.__mailbox is other.__mailbox and self.__id == other.__id

    def __hash__(self) -> int:
        return self.id

    def close(self):
        self.__mailbox.socket_close(self.__id)

    def connect(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        self.__mailbox.socket_connect(self.__id, local_endpoint, remote_endpoint)

    def listen(self, local_endpoint: Endpoint):
        self.__mailbox.socket_listen(self.__id, local_endpoint)

    def accept(self, timeout: float = None) -> Optional[Socket]:
        id = self.__mailbox.socket_accept(self.__id, timeout)
        if id == -1:  # timeout
            return None
        return Socket(self.__mailbox, id)

    def send(self, buf: bytes) -> int:
        return self.__mailbox.socket_send(self.__id, buf)

    def recv(self, max_size: int, timeout: Optional[float] = None) -> bytes:
        return self.__mailbox.socket_recv(self.__id, max_size, timeout)

    def recv_exact(self, size: int, timeout: Optional[float] = None) -> bytes:
        ret = b''
        while size and (timeout is None or timeout > 0):
            start = time.time()
            seg = self.__mailbox.socket_recv(self.__id, size, timeout)
            ret += seg
            size -= len(seg)
            if timeout is not None:
                timeout -= time.time() - start
        return ret

    @property
    def mailbox(self) -> Mailbox:
        return self.__mailbox

    @property
    def id(self) -> int:
        return self.__id
