import email
import pytest
from faker import Faker
from src.tom import Endpoint
from src.tom.mailbox._packet import Packet
from src.config import config


def make_msg_txt(
        from_=b'port A <foo@bar.com>',
        to=b'port B <bar@foo.com>',
        seq=b'123',
        attempt=b'456',
        xmailer=bytes(config['tom']['X-Mailer'], 'ascii'),
        acks=b'123-0|456-999|789-1|1111-234',
        payload=b'asdfghjklqwertyuiopzxcvbnm'):
    return b'Content-Type: multipart/mixed; boundary="===============5805447368894275178=="\r\nFrom: %b\r\nTo: %b\r\nSubject: %b-%b\r\nX-Mailer: %b\r\n\r\n--===============5805447368894275178==\nContent-Type: application/mailim-acks\nMIME-Version: 1.0\nContent-Transfer-Encoding: quoted-printable\n\n%b\n--===============5805447368894275178==\r\nnContent-Type: application/mailim-payload\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%b\r\n--===============5805447368894275178==--\r\n'\
        % (from_, to, seq, attempt, xmailer, acks, payload)


def test_from_message(faker: Faker):
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    seq = faker.pyint()
    attempt = faker.pyint()
    acks = faker.pylist(10, False, int)
    acks = set(zip(acks[0::2], acks[1::2]))
    payload = faker.binary(111)
    msg_txt = make_msg_txt(
        from_=bytes('{} <{}>'.format(from_.port, from_.address), 'ascii'),
        to=bytes('{} <{}>'.format(to.port, to.address), 'ascii'),
        seq=b'%d' % seq,
        attempt=b'%d' % attempt,
        acks=b'|'.join(b'%d-%d' % ack for ack in acks),
        payload=payload)
    msg = email.message_from_bytes(msg_txt)
    packet = Packet.from_message(msg)
    assert packet.from_ == from_
    assert packet.to == to
    assert packet.seq == seq
    assert packet.attempt == attempt
    assert packet.acks == acks
    assert packet.payload == payload


def test_from_message_invalid_mailer(faker: Faker):
    msg_txt = make_msg_txt(xmailer=b'!'+bytes(config['tom']['X-Mailer'], 'ascii'))
    msg = email.message_from_bytes(msg_txt)
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid X-Mailer header')


def test_from_message_invalid_tid(faker: Faker):
    msg_txt = make_msg_txt(seq=b'!')
    msg = email.message_from_bytes(msg_txt)
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid tid')


def test_from_message_invalid_acks(faker: Faker):
    msg_txt = make_msg_txt(acks=b'!')
    msg = email.message_from_bytes(msg_txt)
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid acks')


def test_to_message(faker: Faker):
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    seq = faker.pyint()
    attempt = faker.pyint()
    acks = set((faker.pyint(), faker.pyint()) for i in range(10))
    payload = faker.binary(111)
    packet = Packet(from_, to, seq, attempt, acks, payload)
    msg = packet.to_message()
    assert msg.get('From') == '{} <{}>'.format(from_.port, from_.address)
    assert msg.get('To') == '{} <{}>'.format(to.port, to.address)
    assert msg.get('Subject') == '-'.join(map(str, (seq, attempt)))
    assert msg.get('X-Mailer') == config['tom']['X-Mailer']
    assert len(msg.get_payload()) == 2
    assert msg.get_payload()[0].get('Content-Type') == 'application/x-mailim-acks'
    assert msg.get_payload()[0].get_payload() == '|'.join('-'.join(map(str, ack)) for ack in acks)
    assert msg.get_payload()[1].get('Content-Type') == 'application/x-mailim-payload'
    assert msg.get_payload()[1].get_payload(decode=True) == payload


def test_negative_seq(faker: Faker):
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    packet = Packet(from_, to, -1, 0, {(0, 0)}, b'')
    recovered_packet = Packet.from_message(packet.to_message())
    assert recovered_packet.seq == -1


def test_line_ending(faker: Faker):
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    payload = b'abc\r123\ndef\r\n456\n\rxyz'
    packet = Packet(from_, to, 0, 0, set(), payload)
    msg = packet.to_message()
    bytes_ = msg.as_bytes()
    recovered_msg = email.message_from_bytes(bytes_)
    recovered_packet = Packet.from_message(recovered_msg)
    assert recovered_packet.payload == payload
