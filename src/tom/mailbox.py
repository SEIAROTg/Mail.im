from typing import Optional
import threading
import smtplib
import imapclient
from . import Credential, Endpoint


class Mailbox:
    __closed: bool = False
    __next_socket_id = 0
    __mutex: threading.Lock

    __transport: smtplib.SMTP
    __store: imapclient.IMAPClient

    def __init__(self, smtp: Credential, imap: Credential):
        self.__mutex = threading.Lock()

        self.__transport = smtplib.SMTP(smtp.host, smtp.port)
        self.__transport.ehlo()
        self.__transport.starttls()
        self.__transport.login(smtp.username, smtp.password)

        self.__store = imapclient.IMAPClient(imap.host, imap.port, ssl=True, use_uid=True)
        self.__store.login(imap.username, imap.password)

    def __del__(self):
        self.close()

    def close(self):
        with self.__mutex:
            if self.__closed:
                return
            self.__closed = True
            self.__transport.close()
            self.__store.logout()

    def socket_create(self) -> int:
        with self.__mutex:
            sid = self.__next_socket_id
            self.__next_socket_id += 1
            return sid

    def socket_close(self, sid: int):
        # TODO
        pass

    def socket_connect(self, sid: int, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        # TODO
        pass

    def socket_listen(self, sid: int, local_endpoint: Endpoint):
        # TODO
        pass

    def socket_accept(self, sid: int, timeout: Optional[float]) -> int:
        # TODO
        pass

    def socket_send(self, sid: int, buf: bytes) -> int:
        # TODO
        pass

    def socket_recv(self, sid: int, size: int, timeout: Optional[float]) -> Optional[bytes]:
        # TODO
        pass
