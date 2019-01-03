from typing import Optional, Dict, Tuple
import threading
import smtplib
import imapclient
from . import Credential, Endpoint
from .socket_context import *
from .packet import Packet


class Mailbox:
    __closed: bool = False
    __next_socket_id = 0
    __sockets: Dict[int, SocketContext]
    __connected_sockets: Dict[Tuple[Endpoint, Endpoint], int]
    __mutex: threading.RLock

    __transport: smtplib.SMTP
    __store: imapclient.IMAPClient

    def __init__(self, smtp: Credential, imap: Credential):
        self.__sockets = {}
        self.__connected_sockets = {}
        self.__mutex = threading.RLock()

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
            self.__sockets[sid] = SocketContext()
            return sid

    def socket_close(self, sid: int):
        with self.__mutex:
            if sid in self.__sockets:
                del self.__sockets[sid]

    def socket_connect(self, sid: int, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        with self.__mutex:
            self.__socket_check_status(sid, SocketStatus.CREATED)
            if (local_endpoint, remote_endpoint) in self.__connected_sockets:
                raise Exception('address already in use')
            self.__connected_sockets[(local_endpoint, remote_endpoint)] = sid
            self.__sockets[sid] = SocketContextConnected(local_endpoint, remote_endpoint)

    def socket_listen(self, sid: int, local_endpoint: Endpoint):
        # TODO
        pass

    def socket_accept(self, sid: int, timeout: Optional[float]) -> int:
        # TODO
        pass

    def socket_send(self, sid: int, buf: bytes) -> int:
        context: SocketContextConnected = self.__socket_check_status(sid, SocketStatus.CONNECTED)
        seq = context.next_seq
        context.next_seq += 1
        packet = Packet(seq, buf)
        msg = packet.to_message()
        # TODO: escape port
        msg.add_header('From', '"{}" <{}>'.format(context.local_endpoint.port, context.local_endpoint.address))
        msg.add_header('To', '"{}" <{}>'.format(context.remote_endpoint.port, context.remote_endpoint.address))
        self.__transport.sendmail(context.local_endpoint.address, context.remote_endpoint.address, msg.as_bytes())
        return len(buf)

    def socket_recv(self, sid: int, size: int, timeout: Optional[float]) -> Optional[bytes]:
        # TODO
        pass

    def __socket_check_status(self, sid: int, status: SocketStatus) -> SocketContext:
        if not sid in self.__sockets:
            raise Exception('socket does not exist')
        context = self.__sockets[sid]
        if context.status != status:
            raise Exception('invalid status of socket: expected "{}", got "{}"'
                            .format(status, context.status))
        return context
