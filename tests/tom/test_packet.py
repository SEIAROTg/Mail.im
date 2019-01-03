import email
import pytest
from faker import Faker
from src.tom.packet import Packet
from src.config import config


@pytest.fixture()
def faker() -> Faker:
    return Faker()


def test_from_message(faker: Faker):
    seq = faker.pyint()
    payload = faker.binary(111)
    msg_txt = b'Content-Type: multipart/mixed; boundary="===============5805447368894275178=="\r\nSubject: %b\r\nX-Mailer: %b\r\n\r\n--===============5805447368894275178==\r\nnContent-Type: application/mailim-payload\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%b\r\n--===============5805447368894275178==--\r\n'\
              % (bytes(str(seq), 'ascii'), bytes(config['tom']['X-Mailer'], 'ascii'), payload)
    msg = email.message_from_bytes(msg_txt)
    packet = Packet.from_message(msg)
    assert packet.seq == seq
    assert packet.payload == payload


def test_from_message_invalid_mailer(faker: Faker):
    seq = faker.pyint()
    payload = faker.binary(111)
    msg_txt = b'Content-Type: multipart/mixed; boundary="===============5805447368894275178=="\r\nSubject: %b\r\nX-Mailer: %b\r\n\r\n--===============5805447368894275178==\r\nnContent-Type: application/mailim-payload\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%b\r\n--===============5805447368894275178==--\r\n' \
              % (bytes(str(seq), 'ascii'), b'!' + bytes(config['tom']['X-Mailer'], 'ascii'), payload)
    msg = email.message_from_bytes(msg_txt)
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid packet')


def test_from_message_invalid_seq(faker: Faker):
    seq = faker.pyint()
    payload = faker.binary(111)
    msg_txt = b'Content-Type: multipart/mixed; boundary="===============5805447368894275178=="\r\nSubject: %b\r\nX-Mailer: %b\r\n\r\n--===============5805447368894275178==\r\nnContent-Type: application/mailim-payload\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%b\r\n--===============5805447368894275178==--\r\n' \
              % (b'!' + bytes(str(seq), 'ascii'), bytes(config['tom']['X-Mailer'], 'ascii'), payload)
    msg = email.message_from_bytes(msg_txt)
    with pytest.raises(Exception) as execinfo:
        Packet.from_message(msg)
    assert execinfo.match('invalid packet')


def test_to_email(faker: Faker):
    seq = faker.pyint()
    payload = faker.binary(111)
    packet = Packet(seq, payload)
    msg = packet.to_message()
    assert msg.get('Subject') == str(seq)
    assert msg.get('X-Mailer') == config['tom']['X-Mailer']
    assert len(msg.get_payload()) == 1
    assert msg.get_payload()[0].get('Content-Type') == 'application/mailim-payload'
    assert msg.get_payload()[0].get_payload(decode=True) == payload
