from ..credential import Credential
from ._mailbox_listener import MailboxListener
from ._mailbox_socket_interface import MailboxSocketInterface
from ._mailbox_epoll_interface import MailboxEpollInterface


class Mailbox(MailboxListener, MailboxSocketInterface, MailboxEpollInterface):
    def __init__(self, smtp: Credential, imap: Credential):
        """
        Initialize and connect to a new mailbox.

        :param smtp: SMTP credential.
        :param imap: IMAP credential.
        """
        super().__init__(smtp=smtp, imap=imap)

    def __del__(self):
        self.close()

    def close(self):
        """
        Close the mailbox and forcefully terminate all communication on it.
        """
        super().close()

    def join(self):
        """
        Join the internal threads.
        """
        super().join()
