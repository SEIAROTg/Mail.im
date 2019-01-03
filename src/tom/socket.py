from . import Mailbox


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
