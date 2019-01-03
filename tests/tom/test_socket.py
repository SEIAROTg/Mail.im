from typing import Tuple
from email.mime.multipart import MIMEMultipart
from unittest.mock import patch, call
import pytest
from faker import Faker
from src.tom import Endpoint, Credential, Mailbox, Socket


@pytest.fixture()
def faker() -> Faker:
    return Faker()


# noinspection PyPep8Naming
@pytest.fixture(autouse=True)
def SMTP():
    with patch('smtplib.SMTP') as fixture:
        yield fixture


# noinspection PyPep8Naming
@pytest.fixture(autouse=True)
def IMAPClient():
    with patch('imapclient.IMAPClient') as fixture:
        yield fixture


# noinspection PyPep8Naming
@pytest.fixture(autouse=True)
def Packet():
    with patch('src.tom.mailbox.Packet') as fixture:
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


def test_send(SMTP, Packet, faker: Faker, mailbox: Mailbox, endpoints: Tuple[Endpoint, Endpoint]):
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
    SMTP.return_value.sendmail.assert_called_once_with(endpoints[0].address, endpoints[1].address, msg.as_bytes())
