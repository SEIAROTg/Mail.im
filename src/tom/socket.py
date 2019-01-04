from __future__ import annotations
from typing import Optional
from . import Mailbox, Endpoint


class Socket:
    __id: int = -1
    __mailbox: Mailbox

    def __init__(self, mailbox: Mailbox):
        self.__mailbox = mailbox
        self.__id = mailbox.socket_create()

    def __del__(self):
        self.close()

    def close(self):
        self.__mailbox.socket_close(self.__id)
        self.__id = -1

    def connect(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        self.__mailbox.socket_connect(self.__id, local_endpoint, remote_endpoint)

    def listen(self, local_endpoint: Endpoint):
        self.__mailbox.socket_listen(self.__id, local_endpoint)

    def accept(self, timeout: float = None) -> Optional[Socket]:
        id = self.__mailbox.socket_accept(self.__id, timeout)
        if id == -1:  # timeout
            return None
        sck = Socket(self.__mailbox)
        sck.__id = id
        return sck

    def send(self, buf: bytes) -> int:
        return self.__mailbox.socket_send(self.__id, buf)

    def recv(self, size: int, timeout: Optional[float] = None) -> bytes:
        return self.__mailbox.socket_recv(self.__id, size, timeout)
