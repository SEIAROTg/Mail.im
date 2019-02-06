import pytest
import time
from faker import Faker
from src.tom import Socket
from src.tom.mailbox._packet import Packet
from ..socket_test_helper import SocketTestHelper


def test_simple(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    socket.shutdown()
    dump = socket.dump()
    Socket.restore(helper.mailbox, dump)


def test_address_in_use(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.shutdown()
    dump = socket.dump()
    socket2 = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket = Socket.restore(helper.mailbox, dump)
    assert execinfo.match('address already in use')


def test_address_in_use2(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)
    with pytest.raises(Exception) as execinfo:
        socket2 = helper.create_connected_socket(*endpoints)
    assert execinfo.match('address already in use')


def test_send_cursor(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    for i in range(100):
        socket.send(payload)
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, set((i, 0) for i in range(100)), b'')})
    time.sleep(0.5)
    for i in range(100):
        helper.assert_sent(Packet(*endpoints, i, 0, set(), payload, is_syn=i==0), 0.5)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    payload = faker.binary(111)
    socket.send(payload)

    helper.assert_sent(Packet(*endpoints, 100, 0, set(), payload, is_syn=True), 0.5)


@pytest.mark.timeout(5)
def test_recv_cursor(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    messages = {
        i: Packet(*reversed(endpoints), i, 0, set(), payload) for i in range(100)
    }
    helper.feed_messages(messages)
    time.sleep(1.5)
    socket.recv_exact(111 * 40 + 50)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    assert socket.recv_exact(111 * 60 - 50) == payload[50:] + payload * 59


@pytest.mark.timeout(5)
def test_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.send(payload)
    socket.shutdown()
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True), 0.5)
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    helper.assert_sent(Packet(*endpoints, 0, 1, set(), payload, is_syn=True), 0.5)


@pytest.mark.timeout(5)
def test_send_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    socket.recv_exact(111)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_attempt_cursor(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True), 0.5)
    socket.shutdown()
    dump = socket.dump()
    socket = Socket.restore(helper.mailbox, dump)

    helper.assert_sent(Packet(*endpoints, 0, 1, set(), payload, is_syn=True), 0.5)
