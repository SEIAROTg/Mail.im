import email
import pytest
from faker import Faker
from src.tom import Endpoint
from src.tom._mailbox.packet import PlainPacket as Packet
from src.config import config


@pytest.fixture()
def packet(faker: Faker) -> Packet:
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    seq = faker.pyint()
    attempt = faker.pyint()
    acks = set((faker.pyint(), faker.pyint()) for i in range(10))
    payload = faker.binary(111)
    is_syn = faker.pybool()
    return Packet(from_, to, seq, attempt, acks, payload, is_syn)


def test_from_message_invalid_mailer(packet: Packet):
    msg = packet.to_message()
    msg.replace_header('X-Mailer', b'!' + bytes(config['tom']['X-Mailer'], 'ascii'))
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid X-Mailer header')


def test_from_message_invalid_content_type(packet: Packet):
    msg = packet.to_message()
    msg.replace_header('Content-Type', 'application/x-mailim-packet-secure')
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid Content-Type header')


def test_to_message(packet: Packet):
    msg = packet.to_message()
    assert msg.get('Content-Type') == 'application/x-mailim-packet'
    assert msg.get('From') == '{} <{}>'.format(packet.from_.port, packet.from_.address)
    assert msg.get('To') == '{} <{}>'.format(packet.to.port, packet.to.address)
    assert msg.get('X-Mailer') == config['tom']['X-Mailer']


def test_from_to_message(packet: Packet):
    msg = packet.to_message()
    packet_recv = Packet.from_message(msg)
    assert packet_recv == packet


def test_negative_seq(faker: Faker):
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    packet = Packet(from_, to, -1, 0, {(0, 0)}, b'')
    recovered_packet = Packet.from_message(packet.to_message())
    assert recovered_packet.seq == -1


def test_line_ending(packet: Packet):
    payload = b'abc\r123\ndef\r\n456\n\rxyz'
    packet.payload = payload
    msg = packet.to_message()
    bytes_ = msg.as_bytes()
    recovered_msg = email.message_from_bytes(bytes_)
    recovered_packet = Packet.from_message(recovered_msg)
    assert recovered_packet.payload == payload
