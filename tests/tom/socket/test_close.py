import pytest
from faker import Faker
from src.tom._mailbox.packet import PlainPacket as Packet
from ..socket_test_helper import SocketTestHelper


def test_connected(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    helper.create_connected_socket(*endpoints).close()
    helper.create_connected_socket(*endpoints)


def test_listening(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    helper.create_listening_socket(endpoint).close()
    helper.create_listening_socket(endpoint)


@pytest.mark.timeout(5)
def test_unblock_recv(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.recv_exact(100)
    assert execinfo.match('already closed')
    thread.join()


@pytest.mark.timeout(5)
def test_unblock_accept(helper: SocketTestHelper):
    socket = helper.create_listening_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.accept()
    assert execinfo.match('already closed')
    thread.join()


@pytest.mark.timeout(5)
def test_no_recv(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    socket.recv_exact(55)

    socket.close()

    with pytest.raises(Exception) as execinfo:
        socket.recv(1000)
    assert execinfo.match('not exist')


def test_no_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})

    socket.recv_exact(111)
    socket.close()
    helper.assert_not_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5)


def test_no_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.send(payload)

    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True), 0.5)
    socket.close()
    helper.assert_not_sent(Packet(*endpoints, 0, 1, set(), payload, is_syn=True), 1.5)
