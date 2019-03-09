from unittest.mock import patch, DEFAULT
import pytest
import time
from faker import Faker
from xeddsa.implementations.xeddsa25519 import XEdDSA25519
from src.tom import Socket
from src.tom._mailbox.packet import PlainPacket, SecurePacket
from src.crypto.doubleratchet import DoubleRatchet
from ...socket_test_helper import SocketTestHelper


def test_simple(helper: SocketTestHelper):
    socket = helper.create_secure_connected_socket()
    socket.shutdown()
    dump = socket.dump()
    Socket.restore(helper.mailbox, dump)


def test_address_in_use(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    socket.shutdown()
    dump = socket.dump()
    socket2 = helper.create_secure_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket = Socket.restore(helper.mailbox, dump)
    assert execinfo.match('address already in use')


def test_address_in_use2(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)
    with pytest.raises(Exception) as execinfo:
        socket2 = helper.create_secure_connected_socket(*endpoints)
    assert execinfo.match('address already in use')


def test_ratchet(faker: Faker, helper: SocketTestHelper):
    ratchet_dump = faker.binary(100)
    endpoints = helper.fake_endpoints()
    with patch.multiple(DoubleRatchet, serialize=DEFAULT, fromSerialized=DEFAULT):
        DoubleRatchet.serialize.return_value = ratchet_dump
        socket = helper.create_secure_connected_socket(*endpoints)
        socket.shutdown()
        dump = socket.dump()
        DoubleRatchet.serialize.assert_called_once_with()
        socket = Socket.restore(helper.mailbox, dump)
        DoubleRatchet.fromSerialized.assert_called_once_with(ratchet_dump)


def test_xeddsa(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    sign_key_pair = (faker.binary(32), faker.binary(32))
    with patch.object(XEdDSA25519, '__init__', return_value=None):
        socket = helper.create_secure_connected_socket(*endpoints, sign_key_pair)
        XEdDSA25519.__init__.assert_called_once_with(mont_priv=sign_key_pair[0], mont_pub=sign_key_pair[1])
        socket.shutdown()
        dump = socket.dump()
        XEdDSA25519.__init__.reset_mock()
        socket = Socket.restore(helper.mailbox, dump)
        XEdDSA25519.__init__.assert_called_once_with(mont_priv=sign_key_pair[0], mont_pub=sign_key_pair[1])


@pytest.mark.timeout(5)
def test_send_cursor(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_secure_connected_socket(*endpoints)
    # ack local (1, 0) to avoid uncertainty to ack remote (0, 0)
    socket.send(payload)
    helper.feed_messages({uid - 1: SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), -1, 0, {(1, 0)}, b''))})
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)), 0)
    time.sleep(0.5)
    for i in range(100):
        socket.send(payload)
        helper.feed_messages({uid + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), -1, 0, {(i + 2, 0)}, b''))})
    time.sleep(0.5)
    for i in range(100):
        helper.assert_sent(SecurePacket.encrypt(
            PlainPacket(*endpoints, i + 2, 0, set(), payload)), 0)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    payload = faker.binary(111)
    socket.send(payload)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 102, 0, set(), payload, is_syn=True)), 0.5)


@pytest.mark.timeout(5)
def test_recv_cursor(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_secure_connected_socket(*endpoints)
    messages = {
        uid + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), i + 1, 0, set(), payload)) for i in range(100)
    }
    helper.feed_messages(messages)
    time.sleep(0.5)
    socket.recv_exact(111 * 40 + 50)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    assert socket.recv_exact(111 * 60 - 50) == payload[50:] + payload * 59


@pytest.mark.timeout(5)
def test_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    socket.send(payload)
    socket.shutdown()
    helper.assert_sent(
        SecurePacket.encrypt(
            PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)), 0.5)
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)), 0.5)  # secure packet has no attempt


@pytest.mark.timeout(5)
def test_send_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 1, 0, set(), payload))})
    socket.recv_exact(111)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0)}, b'')), 1.5, 0.5)
