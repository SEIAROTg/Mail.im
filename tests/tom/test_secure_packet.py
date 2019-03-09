from typing import Tuple
import email
from unittest.mock import patch, Mock, MagicMock
import pytest
from faker import Faker
import doubleratchet.header
from xeddsa.implementations.xeddsa25519 import XEdDSA25519, XEdDSA
from src.tom import Endpoint
from src.tom._mailbox.packet import PlainPacket, SecurePacket
from src.crypto.doubleratchet import DoubleRatchet, KeyPair
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
    acks = set(zip(faker.pylist(10, False, int), faker.pylist(10, False, int)))
    return SecurePacket(from_, to, acks, dr_header, b'', body, is_syn)


@pytest.fixture()
def plain_packet(faker: Faker) -> PlainPacket:
    from_ = Endpoint(faker.email(), faker.uuid4())
    to = Endpoint(faker.email(), faker.uuid4())
    seq = faker.pyint()
    attempt = 0
    acks = set(zip(faker.pylist(10, False, int), faker.pylist(10, False, int)))
    payload = faker.binary(111)
    is_syn = faker.pybool()
    return PlainPacket(from_, to, seq, attempt, acks, payload, is_syn)


@pytest.fixture()
def mock_secure_packet_body_pb():
    with patch('src.tom._mailbox.packet.packet_pb2.SecurePacketBody') as fixture:
        yield fixture


@pytest.fixture()
def mock_secure_packet_signed_part_pb():
    with patch('src.tom._mailbox.packet.packet_pb2.SecurePacketSignedPart') as fixture:
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
    payload = faker.binary(111)
    is_syn = faker.pybool()
    plain_packet_stub = MagicMock()
    plain_packet_stub.from_ = Mock()
    plain_packet_stub.to = Mock()
    plain_packet_stub.acks = set(zip(faker.pylist(10, False, int), faker.pylist(10, False, int)))
    plain_packet_stub.payload = payload
    plain_packet_stub.is_syn = is_syn
    cipher_stub = {
        'header': doubleratchet.header.Header(faker.binary(77), faker.pyint(), faker.pyint()),
        'ciphertext': faker.binary(111),
    }
    ratchet_stub = MagicMock()
    ratchet_stub.encryptMessage.return_value = cipher_stub
    signature = faker.binary(32)
    xeddsa_stub = MagicMock()
    xeddsa_stub.sign.return_value = signature

    packet = SecurePacket.encrypt(plain_packet_stub, ratchet_stub, xeddsa_stub)

    ratchet_stub.encryptMessage.assert_called_once()
    xeddsa_stub.sign.assert_called_once()
    assert packet.dr_header == cipher_stub['header']
    assert packet.from_ == plain_packet_stub.from_
    assert packet.to == plain_packet_stub.to
    assert packet.is_syn == plain_packet_stub.is_syn
    assert packet.acks == plain_packet_stub.acks
    assert packet.signature == signature
    assert packet.body == cipher_stub['ciphertext']


def test_decrypt(faker: Faker, packet: SecurePacket, mock_secure_packet_body_pb: MagicMock, mock_secure_packet_signed_part_pb: MagicMock):
    signature = faker.binary(32)
    packet.signature = signature
    cleartext_stub = faker.binary(111)
    ratchet_stub = MagicMock()
    ratchet_stub.decryptMessage.return_value = cleartext_stub
    xeddsa_stub = MagicMock()
    xeddsa_stub.verify.return_value = True

    ret = packet.decrypt(ratchet_stub, xeddsa_stub)

    ratchet_stub.decryptMessage\
        .assert_called_once_with(packet.body, packet.dr_header)
    mock_secure_packet_body_pb.return_value\
        .ParseFromString.assert_called_once_with(cleartext_stub)
    xeddsa_stub.verify\
        .assert_called_once_with(mock_secure_packet_signed_part_pb.return_value.SerializeToString.return_value, signature)
    mock_secure_packet_signed_part_pb.return_value.body.CopyFrom\
        .assert_called_once_with(mock_secure_packet_body_pb.return_value)
    header_to_verify = mock_secure_packet_signed_part_pb.return_value.header.CopyFrom.call_args[0][0]
    assert set((ack.seq, ack.attempt) for ack in header_to_verify.acks) == packet.acks
    assert header_to_verify.dh_pub == packet.dr_header.dh_pub
    assert header_to_verify.n == packet.dr_header.n
    assert header_to_verify.pn == packet.dr_header.pn
    assert header_to_verify.is_syn == packet.is_syn

    assert ret.from_ == packet.from_
    assert ret.to == packet.to
    assert ret.seq == mock_secure_packet_body_pb.return_value.id.seq
    assert ret.attempt == 0
    assert ret.is_syn == packet.is_syn
    assert ret.acks == packet.acks
    assert ret.payload == mock_secure_packet_body_pb.return_value.payload


def test_size_obfuscation(faker: Faker):
    payload = faker.binary(111)
    is_syn = faker.pybool()
    plain_packet_stub = MagicMock()
    plain_packet_stub.from_ = Mock()
    plain_packet_stub.to = Mock()
    plain_packet_stub.acks = set(zip(faker.pylist(10, False, int), faker.pylist(10, False, int)))
    plain_packet_stub.payload = payload
    plain_packet_stub.is_syn = is_syn
    cipher_stub = {
        'header': doubleratchet.header.Header(faker.binary(77), faker.pyint(), faker.pyint()),
        'ciphertext': faker.binary(111),
    }
    ratchet_stub = MagicMock()
    ratchet_stub.encryptMessage.return_value = cipher_stub
    signature = faker.binary(32)
    xeddsa_stub = MagicMock()
    xeddsa_stub.sign.return_value = signature

    packet = SecurePacket.encrypt(plain_packet_stub, ratchet_stub, xeddsa_stub)

    assert len(ratchet_stub.encryptMessage.call_args[0][0]) > 3500
    assert len(xeddsa_stub.sign.call_args[0][0]) > 3500


def test_invalid_signature(faker: Faker, packet: SecurePacket, mock_secure_packet_body_pb: MagicMock, mock_secure_packet_signed_part_pb: MagicMock):
    signature = faker.binary(32)
    packet.signature = signature
    cleartext_stub = faker.binary(111)
    ratchet_stub = MagicMock()
    ratchet_stub.decryptMessage.return_value = cleartext_stub
    xeddsa_stub = MagicMock()
    xeddsa_stub.verify.return_value = False

    with pytest.raises(Exception) as execinfo:
        packet.decrypt(ratchet_stub, xeddsa_stub)
    assert execinfo.match('invalid signature')


@pytest.fixture()
def ratchets() -> Tuple[DoubleRatchet, DoubleRatchet]:
    alice_key = KeyPair.generate()
    alice_ratchet = DoubleRatchet(own_key=alice_key)
    bob_ratchet = DoubleRatchet(other_pub=alice_key.pub)
    return alice_ratchet, bob_ratchet


@pytest.fixture()
def xeddsas() -> Tuple[XEdDSA, XEdDSA]:
    bob_sign_key = XEdDSA25519.generate_mont_priv()
    bob_xeddsa = XEdDSA25519(mont_priv=bob_sign_key)
    alice_xeddsa = XEdDSA25519(mont_pub=XEdDSA25519.mont_pub_from_mont_priv(bob_sign_key))
    return alice_xeddsa, bob_xeddsa


def test_encrypt_decrypt(plain_packet: PlainPacket, ratchets, xeddsas):
    alice_ratchet, bob_ratchet = ratchets
    alice_xeddsa, bob_xeddsa = xeddsas

    encrypted_packet = SecurePacket.encrypt(plain_packet, bob_ratchet, bob_xeddsa)
    decryped_packet = SecurePacket.decrypt(encrypted_packet, alice_ratchet, alice_xeddsa)

    assert decryped_packet == plain_packet


def test_encrypt_decrypt_signature(plain_packet: PlainPacket, ratchets, xeddsas):
    alice_ratchet, bob_ratchet = ratchets
    alice_xeddsa, bob_xeddsa = xeddsas
    mallory_ratchet = DoubleRatchet(other_pub=bob_ratchet.other_pub)

    encrypted_packet = SecurePacket.encrypt(plain_packet, bob_ratchet, bob_xeddsa)
    mallory_packet = SecurePacket.encrypt(plain_packet, mallory_ratchet, bob_xeddsa)
    encrypted_packet.body = mallory_packet.body
    encrypted_packet.dr_header = mallory_packet.dr_header

    with pytest.raises(Exception) as execinfo:
        decrypted_packet = SecurePacket.decrypt(encrypted_packet, alice_ratchet, alice_xeddsa)

    assert execinfo.match('invalid signature')


def test_encrypt_handshake_packet(faker: Faker, plain_packet: PlainPacket):
    plain_packet.payload = b''
    plain_packet.acks = set()
    plain_packet.seq = 0
    plain_packet.attempt = 0
    plain_packet.is_syn = True

    ratchet_stub = MagicMock()
    ratchet_stub.pub = faker.binary(32)
    xeddsa_stub = MagicMock()

    packet = SecurePacket.encrypt(plain_packet, ratchet_stub, xeddsa_stub)

    assert packet.from_ == plain_packet.from_
    assert packet.to == plain_packet.to
    assert packet.dr_header.dh_pub == ratchet_stub.pub
    assert packet.dr_header.n == 0
    assert packet.dr_header.pn == 0
    assert packet.acks == set()
    assert packet.signature == xeddsa_stub.sign.return_value
    assert packet.body == b''
    assert packet.is_syn
    ratchet_stub.encryptMessage.assert_not_called()


def test_decrypt_handshake_packet(faker: Faker, packet: SecurePacket):
    pub = faker.binary(32)
    packet.acks = set()
    packet.dr_header = doubleratchet.header.Header(pub, 0, 0)
    packet.body = b''
    packet.signature = faker.binary(32)
    packet.is_syn = True

    ratchet_stub = MagicMock()
    xeddsa_stub = MagicMock()

    plain_packet = packet.decrypt(ratchet_stub, xeddsa_stub)

    assert plain_packet.from_ == packet.from_
    assert plain_packet.to == packet.to
    assert plain_packet.acks == set()
    assert plain_packet.seq == 0
    assert plain_packet.attempt == 0
    assert plain_packet.payload == b''
    assert plain_packet.is_syn
    assert xeddsa_stub.verify.call_args[0][1] == packet.signature
    ratchet_stub.decryptedMessage.assert_not_called()


def test_encrypt_decrypt_handshake_packet(faker: Faker, plain_packet: PlainPacket, ratchets, xeddsas):
    plain_packet.payload = b''
    plain_packet.acks = set()
    plain_packet.seq = 0
    plain_packet.attempt = 0
    plain_packet.is_syn = True

    alice_ratchet, bob_ratchet = ratchets
    alice_xeddsa, bob_xeddsa = xeddsas

    encrypted_packet = SecurePacket.encrypt(plain_packet, bob_ratchet, bob_xeddsa)
    decrypted_packet = encrypted_packet.decrypt(alice_ratchet, alice_xeddsa)

    assert decrypted_packet.from_ == plain_packet.from_
    assert decrypted_packet.to == plain_packet.to
    assert decrypted_packet.acks == set()
    assert decrypted_packet.seq == 0
    assert decrypted_packet.attempt == 0
    assert decrypted_packet.payload == b''
    assert decrypted_packet.is_syn


def test_encrypt_decrypt_signature_handshake_packet(faker: Faker, plain_packet: PlainPacket, ratchets, xeddsas):
    plain_packet.payload = b''
    plain_packet.acks = set()
    plain_packet.seq = 0
    plain_packet.attempt = 0
    plain_packet.is_syn = True

    alice_ratchet, bob_ratchet = ratchets
    alice_xeddsa, bob_xeddsa = xeddsas

    encrypted_packet = SecurePacket.encrypt(plain_packet, bob_ratchet, bob_xeddsa)
    mallory_pub = faker.binary(32)
    encrypted_packet.dr_header = doubleratchet.header.Header(mallory_pub, 0, 0)
    with pytest.raises(Exception) as execinfo:
        encrypted_packet.decrypt(alice_ratchet, alice_xeddsa)
    assert execinfo.match('invalid signature')
