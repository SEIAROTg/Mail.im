from __future__ import annotations
import time
from typing import Optional, Callable, Union, Tuple
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

    def shutdown(self):
        """
        Shut down a socket but keep its context
        """
        self.__mailbox.socket_shutdown(self.__id)

    def close(self):
        """
        Close the socket.
        """
        self.__mailbox.socket_close(self.__id)

    def connect(
            self,
            local_endpoint: Endpoint,
            remote_endpoint: Endpoint,
            sign_key_pair: Optional[Tuple[bytes, bytes]] = None,
            timeout: Optional[float] = None):
        """
        Establish connection from a local endpoint to remote endpoint. The socket must not be connected or bound.

        :param local_endpoint: a complete `Endpoint` object as local endpoint.
        :param remote_endpoint: a complete `Endpoint` object as remote endpoint.
        :param sign_key_pair: an optional pair of keys for signature in end-to-end encryption. Specify a pair of
        bytes-like objects for local private sign key and remote public sign key to enable end-to-end encryption, or
        specify `None` to disable.
        :param timeout: handshake timeout. Only applicable to secure connections.
        """
        self.__mailbox.socket_connect(self.__id, local_endpoint, remote_endpoint, sign_key_pair, timeout)

    def listen(self, local_endpoint: Endpoint):
        """
        Bind the socket to address and enable it to accept connections. The socket must not be connected or bound.

        :param local_endpoint: a (possible-incomplete) local endpoint to listen on.
        """
        self.__mailbox.socket_listen(self.__id, local_endpoint)

    def accept(
            self,
            should_accept: Optional[Callable[
                [Endpoint, Endpoint, bool],
                Union[bool, bytes, Tuple[bytes, bytes]]]] = None,
            timeout: Optional[float] = None
    ) -> Optional[Socket]:
        """
        Accept an incoming connection. The socket must be bound and listening.

        :param should_accept: a function that decides whether to accept the connection. This function will be given
        three arguments: `local_endpoint: Endpoint`, `remote_endpoint: Endpoint` and `secure: bool`. The possible
        return values are:
            * `False`:  Decline the connection
            * `True`: Accept as a new non-secure connection
            * a bytes-like object: Restore the connection from a dump
            * a pair of bytes-like objects: Accept as a new secure connection with the pair of bytes being local private
              sign key and remote public sign key
        :param timeout: operation timeout in seconds. Omit to wait indefinitely.
        :return: an connected socket.
        """
        id = self.__mailbox.socket_accept(self.__id, should_accept, timeout)
        if id is None:
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
        :param timeout: operation timeout in seconds. Omit to wait indefinitely.
        :return: the data received.
        """
        return self.__mailbox.socket_recv(self.__id, max_size, timeout)

    def recv_exact(self, size: int, timeout: Optional[float] = None) -> bytes:
        """
        Receive data from the socket. The socket must be connected.
        This function will block until `size` bytes of data are received or the socket is closed.

        :param size: the **exact** amount of data to be received.
        :param timeout: operation timeout in seconds. Omit to wait indefinitely.
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

    def dump(self) -> bytes:
        """
        Dump the state of the connected socket.

        :return: socket context information encoded in a bytes-like object.
        """
        return self.mailbox.socket_dump(self.id)

    @classmethod
    def restore(cls, mailbox: Mailbox, dump: bytes):
        """
        Restore a connected socket from dumped context information.

        This will immediately retransmit all pending packets and schedule sending pending acks after ATO.

        :param mailbox: `Mailbox` object the dumped socket belongs to.
        :param dump: dumped data returned by `Socket.dump`.
        :return: the restored socket.
        """
        id = mailbox.socket_restore(dump)
        return cls(mailbox, id)

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
