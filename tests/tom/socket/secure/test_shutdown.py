import pytest
from faker import Faker
from src.tom._mailbox.packet import PlainPacket, SecurePacket
from ...socket_test_helper import SocketTestHelper


def test_connected(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    helper.create_secure_connected_socket(*endpoints).shutdown()
    helper.create_secure_connected_socket(*endpoints)


@pytest.mark.timeout(5)
def test_unblock_recv(helper: SocketTestHelper):
    socket = helper.create_secure_connected_socket()
    thread = helper.defer(socket.shutdown, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.recv_exact(100)
    assert execinfo.match('already closed')
    thread.join()


def test_no_send(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    socket = helper.create_secure_connected_socket()
    socket.shutdown()
    with pytest.raises(Exception) as execinfo:
        socket.send(payload)
    assert execinfo.match('already closed')


@pytest.mark.timeout(5)
def test_no_recv(helper: SocketTestHelper):
    socket = helper.create_secure_connected_socket()
    socket.shutdown()
    with pytest.raises(Exception) as execinfo:
        socket.recv(100)
    assert execinfo.match('already closed')


def test_no_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 1, 0, set(), payload))})

    socket.recv_exact(111)
    socket.shutdown()
    helper.assert_no_packets_sent(1.5)


def test_no_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    socket.send(payload)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)), 0.5)
    socket.shutdown()
    helper.assert_no_packets_sent(1.5)


@pytest.mark.timeout(5)
def test_remaining_data(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 1, 0, set(), payload))})
    socket.recv_exact(55)

    socket.shutdown()

    assert socket.recv_exact(111 - 55) == payload[55:]
