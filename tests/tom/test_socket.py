from typing import Tuple, Optional
import threading
from email.mime.multipart import MIMEMultipart
from unittest.mock import patch, MagicMock, Mock
import imapclient
from imapclient.response_types import Envelope, Address
import pytest
from faker import Faker
from src.tom import Endpoint, Credential, Mailbox, Socket


def make_envelope(from_: Endpoint, to: Endpoint, sender: Optional[Endpoint] = None) -> Envelope:
    if sender is None:
        sender = from_
    return Envelope(
        date=None,
        subject=None,
        from_=[Address(name=from_.port, route=None, mailbox=from_.address, host=None)],
        sender=[Address(name=sender.port, route=None, mailbox=sender.address, host=None)],
        reply_to=None,
        to=[Address(name=to.port, route=None, mailbox=to.address, host=None)],
        cc=None,
        bcc=None,
        in_reply_to=None,
        message_id=None)


@pytest.fixture()
def faker() -> Faker:
    return Faker()


@pytest.fixture(autouse=True)
def transport():
    with patch('smtplib.SMTP') as fixture:
        yield fixture.return_value


@pytest.fixture()
def store():
    return MagicMock()


@pytest.fixture()
def listener():
    fixture = MagicMock()
    fixture.idle_check.side_effect = OSError('no idle check in test')
    return fixture


# noinspection PyPep8Naming
@pytest.fixture(autouse=True)
def IMAPClient(store, listener):
    with patch('imapclient.IMAPClient') as fixture:
        fixture.side_effect = [store, listener]
        yield fixture


# noinspection PyPep8Naming
@pytest.fixture(autouse=True)
def Packet():
    # assume payload is directly fed to mailbox as message
    with patch('src.tom.mailbox.Packet') as fixture, patch('email.message_from_bytes') as message_from_bytes:
        message_from_bytes.side_effect = lambda x: x
        fixture.from_message.side_effect = lambda x: Mock(payload=x)
        yield fixture


@pytest.fixture()
def credential(faker: Faker) -> Credential:
    return Credential(host=faker.hostname(), port=faker.pyint(), username=faker.email(), password=faker.password())


@pytest.fixture()
def endpoints(faker: Faker) -> Tuple[Endpoint, Endpoint]:
    local_endpoint = Endpoint(faker.email(), faker.uuid4())
    remote_endpoint = Endpoint(faker.email(), faker.uuid4())
    return local_endpoint, remote_endpoint


@pytest.fixture()
def mailbox(credential: Credential) -> Mailbox:
    mailbox = Mailbox(credential, credential)
    yield mailbox
    mailbox.close()


@pytest.fixture()
def feed_mailbox(store, listener, request):
    def fixture(messages) -> Tuple[Mailbox, threading.Lock]:
        ready = threading.Lock()

        def idle_check_stub():
            ready.acquire()
            store.fetch.side_effect = [messages]
            listener.idle_check.side_effect = OSError('quit')
            return [(len(messages), b'EXISTS')]

        listener.idle_check.side_effect = idle_check_stub

        ready.acquire()
        mailbox = request.getfixturevalue('mailbox')
        return mailbox, ready

    return fixture


def test_connect(mailbox: Mailbox, endpoints: Tuple[Endpoint, Endpoint]):
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    socket.close()


def test_connect_address_in_use(mailbox: Mailbox, endpoints: Tuple[Endpoint, Endpoint]):
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    socket2 = Socket(mailbox)
    with pytest.raises(Exception) as execinfo:
        socket2.connect(*endpoints)
    assert execinfo.match('address already in use')


def test_connect_invalid_status(mailbox: Mailbox, endpoints: Tuple[Endpoint, Endpoint]):
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket.connect(*reversed(endpoints))
    assert execinfo.match('invalid status of socket')


def test_send(transport, Packet, faker: Faker, mailbox: Mailbox, endpoints: Tuple[Endpoint, Endpoint]):
    msg = MIMEMultipart()
    Packet.return_value.to_message.return_value = msg

    payload = faker.binary(111)
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    socket.send(payload)
    socket.close()

    Packet.assert_called_once_with(0, payload)
    assert msg.get('From') == '"{}" <{}>'.format(endpoints[0].port, endpoints[0].address)
    assert msg.get('To') == '"{}" <{}>'.format(endpoints[1].port, endpoints[1].address)
    transport.sendmail.assert_called_once_with(endpoints[0].address, endpoints[1].address, msg.as_bytes())


@pytest.mark.timeout(5)
def test_recv(feed_mailbox, store, faker: Faker, endpoints: Tuple[Endpoint, Endpoint]):
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload,
        }
    }

    mailbox, ready = feed_mailbox(messages)
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    ready.release()
    ret = socket.recv(len(payload))
    mailbox.close()

    assert ret == payload
    store.add_flags.assert_called_once_with([uid], [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_multiple_packets(feed_mailbox, store, faker: Faker, endpoints: Tuple[Endpoint, Endpoint]):
    payload = faker.binary(300)
    uids = faker.pylist(3, False, int)
    messages = {
        uids[0]: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload[:111]
        },
        uids[1]: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload[111:222]
        },
        uids[2]: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload[222:]
        }
    }

    mailbox, ready = feed_mailbox(messages)
    socket = Socket(mailbox)
    socket.connect(*endpoints)
    ready.release()
    ret = socket.recv(250)
    mailbox.close()

    assert ret == payload[:250]
    store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_multiple_sockets(feed_mailbox, store, faker: Faker, endpoints: Tuple[Endpoint, Endpoint]):
    endpoints2 = (Endpoint(endpoints[0].address, '!' + endpoints[0].port), endpoints[1])
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    envelopes = [make_envelope(*reversed(endpoints)) for i in range(3)]
    envelopes[0].to.clear()
    envelopes[0].to.append(Address(name=endpoints2[0].port, route=None, mailbox=endpoints2[0].address, host=None))
    envelopes[1].to.append(Address(name=endpoints2[0].port, route=None, mailbox=endpoints2[0].address, host=None))

    messages = {
        uids[i]: {
            b'ENVELOPE': envelopes[i],
            b'BODY[]': payloads[i]
        } for i in range(3)
    }

    mailbox, ready = feed_mailbox(messages)
    socket1 = Socket(mailbox)
    socket1.connect(*endpoints)
    socket2 = Socket(mailbox)
    socket2.connect(*endpoints2)
    ready.release()
    ret1 = socket1.recv(107)
    ret2 = socket2.recv(147)
    mailbox.close()

    assert ret1 == payloads[1] + payloads[2]
    assert ret2 == payloads[0] + payloads[1]
    store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_not_connected(feed_mailbox, store, faker: Faker, endpoints: Tuple[Endpoint, Endpoint]):
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload,
        }
    }

    mailbox, ready = feed_mailbox(messages)
    ready.release()
    mailbox.close()

    store.add_flags.assert_not_called()


@pytest.mark.timeout(5)
def test_recv_invalid_packets(feed_mailbox, store, faker: Faker, Packet, endpoints: Tuple[Endpoint, Endpoint]):
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: {
            b'ENVELOPE': make_envelope(*reversed(endpoints)),
            b'BODY[]': payload,
        }
    }
    Packet.from_message.side_effect = Exception('invalid packet')

    mailbox, ready = feed_mailbox(messages)
    ready.release()
    mailbox.close()

    store.add_flags.assert_not_called()
