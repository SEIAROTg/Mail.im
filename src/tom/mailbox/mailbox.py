from ..credential import Credential
from ._mailbox_listener import MailboxListener
from ._mailbox_socket_interface import MailboxSocketInterface


class Mailbox(MailboxListener, MailboxSocketInterface):
    def __init__(self, smtp: Credential, imap: Credential):
        super().__init__(smtp=smtp, imap=imap)

    def __del__(self):
        self.close()

    def close(self):
        super().close()

    def join(self):
        super().join()
