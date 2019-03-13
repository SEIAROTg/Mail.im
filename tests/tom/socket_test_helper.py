from typing import Dict, Tuple, Deque, Optional, Callable, Any, List, Type
from unittest.mock import patch, MagicMock, Mock, _patch
from collections import deque
import time
import threading
from imapclient import SEEN
from imapclient.response_types import Envelope, Address
from faker import Faker
import doubleratchet.header
from src.tom import Mailbox, Credential, Endpoint, Socket, Epoll
from src.tom._mailbox.packet import Packet, PlainPacket, SecurePacket
from src.crypto.doubleratchet import KeyPair


def packet_from_message_stub(cls: Type[Packet]):
    def stub(packet: Packet):
        if not isinstance(packet, cls):
            raise Exception('invalid packet')
        return packet
    return stub


class SocketTestHelper:
    __mutex: threading.RLock
    __sem_send: threading.Semaphore
    __cv_listen: threading.Condition

    __faker: Faker
    __messages: Dict[int, Packet]
    __send_queue: Deque[Packet]
    __closed: bool = False

    mock_store: MagicMock
    mock_listener: MagicMock
    mock_transport: MagicMock
    __mock_imapclient: MagicMock
    __mock_message_from_bytes: MagicMock
    __patches: List[_patch]
    mailbox: Mailbox

    mock_config: Dict

    def __init__(self):
        self.__mutex = threading.RLock()
        self.__sem_send = threading.Semaphore(0)
        self.__cv_listen = threading.Condition(self.__mutex)
        self.__faker = Faker()
        self.__messages = {}
        self.__send_queue = deque()
        self.mock_config = {
            'tom': {
                'X-Mailer': 'Mail.im',
                'RTO': 1000,
                'ATO': 1000,
                'MaxAttempts': 2,
            }
        }
        patch_config = patch.dict('src.config.config', self.mock_config)
        patch_config.start()
        self.mock_store = MagicMock()
        self.mock_store.search.side_effect = self.__search_stub
        self.mock_store.fetch.side_effect = self.__fetch_stub
        self.mock_store.add_flags.side_effect = self.__add_flags_stub
        self.mock_listener = MagicMock()
        idle_check_stub = self.__idle_check_stub()
        self.mock_listener.idle_check.side_effect = lambda *args, **kwargs: next(idle_check_stub, None)
        self.__patches = [
            patch_config,
            patch('smtplib.SMTP', **{'return_value.sendmail.side_effect': self.__sendmail_stub}),
            patch('src.tom._mailbox.imapclient.IMAPClient', side_effect=[self.mock_store, self.mock_listener]),
            patch.object(PlainPacket, 'from_message', packet_from_message_stub(PlainPacket)),
            patch.object(PlainPacket, 'to_message', lambda x: Mock(as_bytes=lambda: x)),
            patch.object(SecurePacket, 'from_message', packet_from_message_stub(SecurePacket)),
            patch.object(SecurePacket, 'to_message', lambda x: Mock(as_bytes=lambda: x)),
            patch.object(SecurePacket, 'decrypt', lambda x, *args: x.body),
            patch.object(SecurePacket, 'encrypt', self.__secure_packet_encrypt_stub),
            patch.object(KeyPair, 'generate', lambda: KeyPair()),
            patch('email.message_from_bytes', lambda x: x),
        ]
        for patch_ in self.__patches:
            patch_.start()
        self.mailbox = Mailbox(self.__fake_credential(), self.__fake_credential())

    def __del__(self):
        self.close()

    def close(self):
        with self.__cv_listen:
            self.__closed = True
            self.__cv_listen.notify_all()
        self.mailbox.close()
        self.mailbox.join()
        for patch_ in self.__patches:
            patch_.stop()
        self.__patches = []

    def create_connected_socket(
            self,
            local_endpoint: Optional[Endpoint] = None,
            remote_endpoint: Optional[Endpoint] = None):
        socket = Socket(self.mailbox)
        local_endpoint = local_endpoint or self.fake_endpoint()
        remote_endpoint = remote_endpoint or self.fake_endpoint()
        socket.connect(local_endpoint, remote_endpoint)
        assert socket.endpoints == (local_endpoint, remote_endpoint)
        return socket

    def create_secure_connected_socket(
            self,
            local_endpoint: Optional[Endpoint] = None,
            remote_endpoint: Optional[Endpoint] = None,
            sign_key_pair: Optional[Tuple[bytes, bytes]] = (None, None),
            timeout: Optional[float] = None):
        socket = Socket(self.mailbox)
        local_endpoint = local_endpoint or self.fake_endpoint()
        remote_endpoint = remote_endpoint or self.fake_endpoint()
        socket.connect(local_endpoint, remote_endpoint, sign_key_pair, timeout=timeout)
        self.assert_sent(self.__secure_packet_encrypt_stub(
            PlainPacket(local_endpoint, remote_endpoint, 0, 0, set(), b'', is_syn=True)), 0.5)
        assert socket.endpoints == (local_endpoint, remote_endpoint)
        return socket

    def create_listening_socket(self, local_endpoint: Optional[Endpoint] = None):
        socket = Socket(self.mailbox)
        local_endpoint = local_endpoint or self.fake_endpoint()
        socket.listen(local_endpoint)
        assert socket.endpoints == (local_endpoint, None)
        return socket

    def create_epoll(self) -> Epoll:
        return Epoll(self.mailbox)

    def feed_messages(self, messages: Dict[int, Packet]):
        assert messages, 'feeding no messages'
        with self.__cv_listen:
            self.__messages.update(messages)
            self.__cv_listen.notify(1)

    def defer(self, func: Callable[[], Any], delay: float):

        def target():
            time.sleep(delay)
            func()

        thread = threading.Thread(target=target)
        thread.start()
        return thread

    def assert_sent(self, packet: Packet, timeout: float = None, min_time: float = None):
        start = time.time()
        assert self.__sem_send.acquire(timeout=timeout), 'packet has not been sent in time'
        with self.__mutex:
            sent_packet = self.__send_queue.popleft()
            assert sent_packet == packet, 'packet has not been sent in time'
            assert not min_time or start + min_time < time.time(), 'packet was sent too early'

    def assert_not_sent(self, packet: Packet, timeout: float = 0):
        time.sleep(timeout)
        with self.__mutex:
            for sent_packet in self.__send_queue:
                assert sent_packet != packet, 'packet has been sent'

    def assert_no_packets_sent(self, timeout: float = 0):
        time.sleep(timeout)
        with self.__mutex:
            assert not self.__send_queue

    def __sendmail_stub(self, from_address, to_address, packet: Packet):
        assert from_address == packet.from_.address
        assert to_address == packet.to.address
        with self.__mutex:
            self.__send_queue.append(packet)
        self.__sem_send.release()
        if isinstance(packet, SecurePacket) and packet.body == b'' and packet.is_syn:
            # is handshake
            dh_pub = self.__faker.binary(32)
            header = doubleratchet.header.Header(dh_pub, 0, 0)
            plain = PlainPacket(packet.to, packet.from_, 0, 0, set(), b'')
            response = SecurePacket(packet.to, packet.from_, set(), header, b'', plain)
            self.feed_messages({-1:  response})

    def __idle_check_stub(self):
        with self.__cv_listen:
            while True:
                if self.__closed:
                    return
                if self.__messages:
                    yield [(len(self.__messages), b'EXISTS')]
                self.__cv_listen.wait()

    def __search_stub(self, criteria):
        assert criteria == 'UNSEEN', 'unsupported search criteria'
        with self.__mutex:
            return list(self.__messages.keys())

    def __fetch_stub(self, uids, data):
        with self.__mutex:
            return {
                uid: {
                    b'ENVELOPE': self.__make_envelope(self.__messages[uid]),
                    b'BODY[]': self.__messages[uid],
                } for uid in uids
            }

    def __add_flags_stub(self, uids, flags):
        assert flags == [SEEN], 'unsupported flags'
        with self.__mutex:
            self.__messages = {uid: packet for uid, packet in self.__messages.items() if uid not in uids}

    @staticmethod
    def __secure_packet_encrypt_stub(plain_packet: PlainPacket, *args):
        if plain_packet.seq == 0 and plain_packet.is_syn:
            body = b''
        else:
            body = plain_packet
        return SecurePacket(
            plain_packet.from_,
            plain_packet.to,
            set(plain_packet.acks),
            doubleratchet.header.Header(None, 0, 0),
            b'',
            body,
            plain_packet.is_syn)

    def __fake_credential(self) -> Credential:
        return Credential(
            host=self.__faker.hostname(),
            port=self.__faker.pyint(),
            username=self.__faker.email(),
            password=self.__faker.password())

    def fake_endpoint(self) -> Endpoint:
        return Endpoint(self.__faker.email(), self.__faker.uuid4())

    def fake_endpoints(self) -> Tuple[Endpoint, Endpoint]:
        return self.fake_endpoint(), self.fake_endpoint()

    @staticmethod
    def __make_envelope(packet: Packet) -> Envelope:
        return Envelope(
            date=None,
            subject=None,
            from_=[Address(name=packet.from_.port, route=None, mailbox=packet.from_.address, host=None)],
            sender=[Address(name=packet.from_.port, route=None, mailbox=packet.from_.address, host=None)],
            reply_to=None,
            to=[Address(name=packet.to.port, route=None, mailbox=packet.to.address, host=None)],
            cc=None,
            bcc=None,
            in_reply_to=None,
            message_id=None)

    @staticmethod
    def default_should_accept_secure(*args):
        return (None, None)
