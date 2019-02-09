import email
from unittest.mock import patch, Mock, MagicMock
import pytest
from faker import Faker
import doubleratchet.header
from src.tom import Endpoint
from src.tom._mailbox.packet import SecurePacket
from src.config import config


@pytest.fixture()
def packet(faker: Faker) -> SecurePacket:
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    dh_pub = faker.binary(32)
    n = faker.pyint()
    pn = faker.pyint()
    dr_header = doubleratchet.header.Header(dh_pub, n, pn)
    body = faker.binary(111)
    is_syn = faker.pybool()
    return SecurePacket(from_, to, dr_header, body, is_syn)


@pytest.fixture()
def mock_plain_packet_pb():
    with patch('src.tom._mailbox.packet.packet_pb2.PlainPacket') as fixture:
        yield fixture


@pytest.fixture()
def mock_plain_packet():
    with patch('src.tom._mailbox.packet.secure_packet.PlainPacket') as fixture:
        yield fixture


def test_from_message_invalid_mailer(packet: SecurePacket):
    msg = packet.to_message()
    msg.replace_header('X-Mailer', b'!' + bytes(config['tom']['X-Mailer'], 'ascii'))
    with pytest.raises(Exception) as execinfo:
        SecurePacket.from_message(msg)
    assert execinfo.match('invalid X-Mailer header')


def test_from_message_invalid_content_type(packet: SecurePacket):
    msg = packet.to_message()
    msg.replace_header('Content-Type', 'application/x-mailim-packet')
    with pytest.raises(Exception) as execinfo:
        SecurePacket.from_message(msg)
    assert execinfo.match('invalid Content-Type header')


def test_to_message(packet: SecurePacket):
    msg = packet.to_message()
    assert msg.get('Content-Type') == 'application/x-mailim-packet-secure'
    assert msg.get('From') == '{} <{}>'.format(packet.from_.port, packet.from_.address)
    assert msg.get('To') == '{} <{}>'.format(packet.to.port, packet.to.address)
    assert msg.get('X-Mailer') == config['tom']['X-Mailer']


def test_from_to_message(packet: SecurePacket):
    msg = packet.to_message()
    packet_recv = SecurePacket.from_message(msg)
    assert packet_recv == packet


def test_line_ending(packet: SecurePacket):
    body = b'abc\r123\ndef\r\n456\n\rxyz'
    packet.body = body
    msg = packet.to_message()
    bytes_ = msg.as_bytes()
    recovered_msg = email.message_from_bytes(bytes_)
    recovered_packet = SecurePacket.from_message(recovered_msg)
    assert recovered_packet.body == body


def test_encrypt(faker: Faker):
    serialized_body_stub = faker.binary(133)
    body_stub = MagicMock()
    body_stub.SerializeToString.return_value = serialized_body_stub
    plain_packet_stub = MagicMock()
    plain_packet_stub.to_pb.return_value.body = body_stub
    plain_packet_stub.is_syn = Mock()
    plain_packet_stub.from_ = Mock()
    plain_packet_stub.to = Mock()
    cipher_stub = {
        'header': Mock(),
        'ciphertext': faker.binary(111),
    }
    ratchet_stub = MagicMock()
    ratchet_stub.encryptMessage.return_value = cipher_stub

    packet = SecurePacket.encrypt(plain_packet_stub, ratchet_stub)

    ratchet_stub.encryptMessage.assert_called_once_with(serialized_body_stub)
    assert packet.dr_header == cipher_stub['header']
    assert packet.from_ == plain_packet_stub.from_
    assert packet.to == plain_packet_stub.to
    assert packet.is_syn == plain_packet_stub.is_syn
    assert packet.body == cipher_stub['ciphertext']


def test_decrypt(faker: Faker, packet: SecurePacket, mock_plain_packet_pb: MagicMock, mock_plain_packet: MagicMock):
    cleartext_stub = faker.binary(111)
    packet.is_syn = Mock()
    ratchet_stub = MagicMock()
    ratchet_stub.decryptMessage.return_value = cleartext_stub
    plain_packet_pb_stub = mock_plain_packet_pb.return_value
    mock_plain_packet.from_pb.return_value = Mock()

    ret = packet.decrypt(ratchet_stub)

    assert plain_packet_pb_stub.is_syn == packet.is_syn
    plain_packet_pb_stub.body.ParseFromString.called_once_with(cleartext_stub)
    mock_plain_packet.from_pb.assert_called_once_with((packet.from_, packet.to), plain_packet_pb_stub)
    assert ret == mock_plain_packet.from_pb.return_value
