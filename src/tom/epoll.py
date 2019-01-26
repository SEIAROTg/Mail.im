from typing import Set, Tuple, Optional
from .mailbox import Mailbox
from .socket import Socket


class Epoll:
    __mailbox: Mailbox
    __id: int

    def __init__(self, mailbox: Mailbox):
        """
        Create an epoll object

        :param mailbox: the mailbox to register epoll object with
        """
        self.__mailbox = mailbox
        self.__id = mailbox.epoll_create()

    def add(self, rset: Set[Socket], xset: Set[Socket]):
        """
        Add sockets to epoll object

        All supplied sockets must belong to the supplied mailbox; otherwise, the behavior is undefined

        :param rset: a set of sockets whose READ ready status is to be polled
        :param xset: a set of sockets whose ERROR ready status is to be polled
        """
        self.__mailbox.epoll_add(
            self.__id,
            set(socket.id for socket in rset),
            set(socket.id for socket in xset))

    def remove(self, rset: Set[Socket], xset: Set[Socket]):
        """
        Remove sockets from epoll object

        All supplied sockets must belong to the supplied mailbox; otherwise, the behavior is undefined
        
        Sockets not currently in the epoll object will be ignored

        :param rset: a set of sockets whose READ ready status is not to be polled
        :param xset: a set of sockets whose ERROR ready status is not to be polled
        """
        self.__mailbox.epoll_remove(
            self.__id,
            set(socket.id for socket in rset),
            set(socket.id for socket in xset))

    def close(self):
        """
        Unregister the epoll object with mailbox
        
        This will immediately unblocks `wait` calls, if any
        """
        self.__mailbox.epoll_close(self.__id)

    def wait(self, timeout: Optional[float] = None) -> Tuple[Set[Socket], Set[Socket]]:
        """
        Wait until any registered socket is ready, or operation is timed out, whichever happens first

        :param timeout: a floating point number specifying timeout for the operation in seconds; or `None` for no
        timeout
        :return: a pair of sets of `Socket` that are ready, subsets of the supplied `rset` and `xset`
        """
        rrset, rxset = self.__mailbox.epoll_wait(self.__id, timeout)
        return set(Socket(self.__mailbox, sid) for sid in rrset), set(Socket(self.__mailbox, sid) for sid in rxset)
