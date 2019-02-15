import pytest
from ..socket_test_helper import SocketTestHelper
from faker import Faker
from src.tom._mailbox.packet import PlainPacket as Packet


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    socket = helper.create_connected_socket(*endpoints)
    packet = Packet(*endpoints, 0, 0, set(), payload, is_syn=True)

    socket.send(payload)
    socket.close()

    helper.assert_sent(packet)


@pytest.mark.timeout(5)
def test_syn(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    socket = helper.create_connected_socket(*endpoints)
    packet0 = Packet(*endpoints, 0, 0, set(), payload, is_syn=True)
    packet1 = Packet(*endpoints, 1, 0, set(), payload, is_syn=False)

    socket.send(payload)
    socket.send(payload)
    socket.close()

    helper.assert_sent(packet0)
    helper.assert_sent(packet1)


@pytest.mark.timeout(5)
def test_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True))
    helper.assert_sent(Packet(*endpoints, 0, 1, set(), payload, is_syn=True), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_no_retransmit_after_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, {(0, 0)}, b'')})
    helper.assert_not_sent(Packet(*endpoints, 0, 1, set(), payload, is_syn=True), 1.5)
    helper.assert_not_sent(Packet(*endpoints, 0, 1, {(-1, 0)}, payload, is_syn=True))


@pytest.mark.timeout(5)
def test_max_attempts(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    socket = helper.create_connected_socket()

    socket.send(payload)
    with pytest.raises(Exception) as execinfo:
        socket.recv(100)
    assert execinfo.match('socket already closed')


@pytest.mark.timeout(5)
def test_many_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    socket = helper.create_connected_socket(*endpoints)

    for i in range(5000):
        socket.send(payload)
        helper.feed_messages({uid + i: Packet(*reversed(endpoints), -1, 0, {(i, 0)}, b'')})
