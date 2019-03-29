from typing import Set, Optional, Tuple, List
import time
from .mailbox_base import MailboxBase
from .epoll_context import EpollContext
from . import socket_context


class MailboxEpollInterface(MailboxBase):
    def epoll_create(self) -> int:
        with self._mutex:
            eid = self._next_epoll_id
            self._next_epoll_id += 1
            self._epolls[eid] = EpollContext()
            return eid

    def epoll_close(self, eid: int):
        context = self.__get_epoll(eid)
        with context.cv:
            self.epoll_remove(eid, set(context.rset), set(context.xset))
            context.closed = True
            context.cv.notify_all()
        with self._mutex:
            del self._epolls[eid]

    def epoll_add(self, eid: int, rset: Set[int], xset: Set[int]):
        context = self.__get_epoll(eid)
        with context.cv:
            context.rset |= rset
            context.xset |= xset
        with self.__lock_sockets(rset) as contexts:
            for socket_context in contexts:
                socket_context.repolls.add(eid)
        with self.__lock_sockets(xset) as contexts:
            for socket_context in contexts:
                socket_context.xepolls.add(eid)

    def epoll_remove(self, eid: int, rset: Set[int], xset: Set[int]):
        context = self.__get_epoll(eid)
        with context.cv:
            context.rset -= rset
            context.xset -= xset
            context.rrset -= rset
            context.rxset -= xset
        with self.__lock_sockets(rset) as contexts:
            for socket_context in contexts:
                socket_context.repolls.remove(eid)
        with self.__lock_sockets(xset) as contexts:
            for socket_context in contexts:
                socket_context.xepolls.remove(eid)

    def epoll_wait(self, eid: int, timeout: Optional[float] = None) -> Tuple[Set[int], Set[int]]:
        context = self.__get_epoll(eid)
        with context.cv:
            while not (context.rrset or context.rxset or context.closed) and (timeout is None or timeout > 0):
                start = time.time()
                context.cv.wait(timeout)
                if timeout is not None:
                    timeout -= time.time() - start
            return set(context.rrset), set(context.rxset)

    def __get_epoll(self, eid: int):
        with self._mutex:
            context = self._epolls.get(eid)
        if not context:
            raise Exception('epoll does not exist')
        return context

    def __lock_sockets(mailbox, sidset: Set[int]):
        sids = sorted(sidset)

        class GetSocket:
            __contexts: List[socket_context.Epollable]

            def __enter__(self) -> List[socket_context.Epollable]:
                with mailbox._mutex:
                    self.__contexts = [mailbox._sockets.get(sid) for sid in sids if isinstance(mailbox._sockets.get(sid), socket_context.Epollable)]
                for context in self.__contexts:
                    context.mutex.acquire()
                return self.__contexts

            def __exit__(self, exc_type, exc_val, exc_tb):
                for context in self.__contexts:
                    context.mutex.release()

        return GetSocket()
