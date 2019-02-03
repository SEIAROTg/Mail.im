from __future__ import annotations
import time
from typing import Optional, List, Tuple
from . import Mailbox, Endpoint


class Socket:
    __id: int = -1
    __mailbox: Mailbox

    def __init__(self, mailbox: Mailbox, id: Optional[int] = None):
        """
        Create new socket.

        :param mailbox: `Mailbox` object to register the socket with.
        :param id: an existing socket id to create a new `Socket` object for that existing socket.
        If provided, no new socket will be created.
        """
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
        """
        Close the socket.
        """
        self.__mailbox.socket_close(self.__id)

    def connect(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        """
        Establish connection from a local endpoint to remote endpoint. The socket must not be connected or bound.

        :param local_endpoint: a complete `Endpoint` object as local endpoint.
        :param remote_endpoint: a complete `Endpoint` object as remote endpoint.
        """
        self.__mailbox.socket_connect(self.__id, local_endpoint, remote_endpoint)

    def listen(self, local_endpoint: Endpoint):
        """
        Bind the socket to address and enable it to accept connections. The socket must not be connected or bound.

        :param local_endpoint: a (possible-incomplete) local endpoint to listen on.
        """
        self.__mailbox.socket_listen(self.__id, local_endpoint)

    def accept(self, timeout: float = None) -> Optional[Socket]:
        """
        Accept an incoming connection. The socket must be bound and listening.

        :param timeout: operation timeout in seconds.
        :return: an connected socket.
        """

        id = self.__mailbox.socket_accept(self.__id, timeout)
        if id == -1:  # timeout
            return None
        return Socket(self.__mailbox, id)

    def send(self, buf: bytes) -> int:
        """
        Send data to the socket. The socket must be connected to a remote socket.

        :param buf: data to send.
        :return: the number of bytes sent.
        """
        return self.__mailbox.socket_send(self.__id, buf)

    def recv(self, max_size: int, timeout: Optional[float] = None) -> bytes:
        """
        Receive data from the socket. The socket must be connected.
        This function will block until there is incoming data to receive or the socket is closed.

        :param max_size: the **maximum** amount of data to be received.
        :param timeout: operation timeout in seconds.
        :return: the data received.
        """
        return self.__mailbox.socket_recv(self.__id, max_size, timeout)

    def recv_exact(self, size: int, timeout: Optional[float] = None) -> bytes:
        """
        Receive data from the socket. The socket must be connected.
        This function will block until `size` bytes of data are received or the socket is closed.

        :param size: the **exact** amount of data to be received.
        :param timeout: operation timeout in seconds.
        :return: the data received.
        """
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
        """
        :return: The mailbox that this socket belongs to.
        """
        return self.__mailbox

    @property
    def id(self) -> int:
        """
        :return: The id of socket. This is unique per mailbox.
        """
        return self.__id
