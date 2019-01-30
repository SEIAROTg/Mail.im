from typing import Dict, Tuple, Deque, Optional, Callable, Any, List
from unittest.mock import patch, MagicMock, Mock, _patch
from collections import deque
import time
import threading
from imapclient import SEEN
from imapclient.response_types import Envelope, Address
from faker import Faker
from src.tom import Mailbox, Credential, Endpoint, Socket, Epoll
from src.tom.mailbox._packet import Packet


class SocketTestHelper:
    __mutex: threading.RLock
    __sem_send: threading.Semaphore
    __cv_listen: threading.Condition
    __thread_mailbox: threading.Thread

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
    __mailbox: Mailbox

    __config_stub = {
        'tom': {
            'X-Mailer': 'Mail.im',
            'RTO': 1000,
            'ATO': 1000,
        }
    }

    def __init__(self):
        self.__mutex = threading.RLock()
        self.__sem_send = threading.Semaphore(0)
        self.__cv_listen = threading.Condition(self.__mutex)
        self.__faker = Faker()
        self.__messages = {}
        self.__send_queue = deque()
        patch_config = patch.dict('src.config.config', self.__config_stub)
        self.mock_config = patch_config.start()
        self.mock_store = MagicMock()
        self.mock_store.search.side_effect = self.__search_stub
        self.mock_store.fetch.side_effect = self.__fetch_stub
        self.mock_store.add_flags.side_effect = self.__add_flags_stub
        self.mock_listener = MagicMock()
        self.mock_listener.idle_check.side_effect = self.__idle_check_stub
        patch_transport = patch('smtplib.SMTP')
        self.mock_transport = patch_transport.start()
        self.mock_transport.return_value.sendmail.side_effect = self.__sendmail_stub
        self.mock_packet = MagicMock()
        self.mock_packet.from_message.side_effect = lambda x: x
        self.mock_packet.side_effect = lambda *args: Mock(to_message=lambda: Mock(as_bytes=lambda: Packet(*args)))
        patch_packet0 = patch('src.tom.mailbox._mailbox_listener.Packet', self.mock_packet)
        patch_packet1 = patch('src.tom.mailbox._mailbox_tasks.Packet', self.mock_packet)
        patch_packet0.start()
        patch_packet1.start()
        patch_imapclient = patch('src.tom.mailbox._imapclient.IMAPClient')
        self.__mock_imapclient = patch_imapclient.start()
        self.__mock_imapclient.side_effect = [self.mock_store, self.mock_listener]
        patch_message_from_bytes = patch('email.message_from_bytes')
        self.__mock_message_from_bytes = patch_message_from_bytes.start()
        self.__mock_message_from_bytes.side_effect = lambda x: x
        self.__mailbox = Mailbox(self.__fake_credential(), self.__fake_credential())
        self.__patches = [
            patch_config,
            patch_transport,
            patch_packet0,
            patch_packet1,
            patch_imapclient,
            patch_message_from_bytes]

        self.__thread_mailbox = threading.Thread(target=self.__mailbox.join)
        self.__thread_mailbox.start()

    def __del__(self):
        self.close()

    def close(self):
        with self.__cv_listen:
            self.__closed = True
            self.__cv_listen.notify_all()
        self.__mailbox.close()
        self.__thread_mailbox.join()
        for patch in self.__patches:
            patch.stop()
        self.__patches = []

    def create_connected_socket(
            self,
            local_endpoint: Optional[Endpoint] = None,
            remote_endpoint: Optional[Endpoint] = None):
        socket = Socket(self.__mailbox)
        local_endpoint = local_endpoint or self.fake_endpoint()
        remote_endpoint = remote_endpoint or self.fake_endpoint()
        socket.connect(local_endpoint, remote_endpoint)
        return socket

    def create_listening_socket(self, local_endpoint: Optional[Endpoint] = None):
        socket = Socket(self.__mailbox)
        local_endpoint = local_endpoint or self.fake_endpoint()
        socket.listen(local_endpoint)
        return socket

    def create_epoll(self) -> Epoll:
        return Epoll(self.__mailbox)

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

    def __sendmail_stub(self, from_address, to_address, packet: Packet):
        assert from_address == packet.from_.address
        assert to_address == packet.to.address
        with self.__mutex:
            self.__send_queue.append(packet)
        self.__sem_send.release()

    def __idle_check_stub(self, timeout=None, selfpipe=None):
        with self.__cv_listen:
            while True:
                if self.__closed:
                    return
                self.__cv_listen.wait()
                if self.__messages:
                    return [(len(self.__messages), b'EXISTS')]

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
