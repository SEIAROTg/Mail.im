import pytest
from faker import Faker
from ...socket_test_helper import SocketTestHelper
from src.tom._mailbox.packet import PlainPacket, SecurePacket


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    socket = helper.create_secure_connected_socket(*endpoints)
    plain_packet = PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)
    secure_packet = SecurePacket.encrypt(plain_packet, None)

    socket.send(payload)
    socket.close()

    helper.assert_sent(secure_packet)


@pytest.mark.timeout(5)
def test_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    plain_packet = PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload)

    socket.send(payload)
    helper.assert_sent(SecurePacket.encrypt(plain_packet, None))
    helper.assert_sent(SecurePacket.encrypt(plain_packet, None), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_no_retransmit_after_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(
        SecurePacket.encrypt(PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload), None))
    helper.feed_messages({faker.pyint(): SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), -1, 0, {(1, 0)}, b''), None)})
    helper.assert_no_packets_sent(1.5)


@pytest.mark.timeout(5)
def test_max_attempts(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    socket = helper.create_secure_connected_socket()

    socket.send(payload)
    with pytest.raises(Exception) as execinfo:
        socket.recv(100)
    assert execinfo.match('socket already closed')


@pytest.mark.timeout(5)
def test_many_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    socket = helper.create_secure_connected_socket(*endpoints)

    for i in range(5000):
        socket.send(payload)
        helper.feed_messages({uid + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), -1, 0, {(i + 1, 0)}, b''), None)})
