import time
import pytest
from faker import Faker
from ...socket_test_helper import SocketTestHelper
from src.tom._mailbox.packet import PlainPacket, SecurePacket


def test_empty(helper: SocketTestHelper):
    socket0 = helper.create_secure_connected_socket()
    socket1 = helper.create_secure_connected_socket()
    socket2 = helper.create_listening_socket()
    sockets = {socket0, socket1, socket2}
    epoll = helper.create_epoll()
    epoll.add(sockets, sockets)

    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), payload), None),
    }), 0.5)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), payload), None),
    }), 0.5)
    socket.recv(111)
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_not_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), payload), None),
    }), 0.5)
    socket.recv(1)
    rrset, rxset = epoll.wait(timeout=0)

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_order(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 2, 0, set(), payload), None),
    })
    rrset, rxset = epoll.wait(timeout=0.5)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_empty_packet(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), b''), None),
    })
    rrset, rxset = epoll.wait(timeout=0.5)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_empty_packet_followed_by_non_empty_packets(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), b''), None),
    }), 0.5)
    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 2, 0, set(), payload), None),
    }), 1)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_empty_packet_followed_by_non_empty_packets_reversed(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, set(), b''), None),
    }), 1)
    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 2, 0, set(), payload), None),
    }), 0.5)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_listening_socket(endpoints[0])
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=True), None),
    }), 0.5)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    uid = faker.pyint()
    endpoints = helper.fake_endpoints()
    socket = helper.create_listening_socket(endpoints[0])
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=True), None)
    handshake_packet.body = b''
    helper.defer(lambda: helper.feed_messages({uid: handshake_packet}), 0.5)
    socket.accept()
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept_not_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    local_endpoint = helper.fake_endpoint()
    endpoints = [helper.fake_endpoint() for i in range(2)]
    uid = faker.pyint()
    socket = helper.create_listening_socket(local_endpoint)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(lambda: helper.feed_messages({
        uid + i: SecurePacket.encrypt(
            PlainPacket(endpoints[i], local_endpoint, 0, 0, set(), payload, is_syn=True), None) for i in range(2)
    }), 0.5)
    socket.accept()
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_error_recv(faker: Faker, helper: SocketTestHelper):
    socket = helper.create_secure_connected_socket()
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.defer(socket.close, 0.5)
    rrset, rxset = epoll.wait()

    assert not rrset
    assert rxset == {socket}


@pytest.mark.timeout(5)
def test_error_max_attempts(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    socket = helper.create_secure_connected_socket()
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    socket.send(payload)
    rrset, rxset = epoll.wait()

    assert not rrset
    assert rxset == {socket}


@pytest.mark.timeout(5)
def test_remove(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, {socket})

    helper.feed_messages({faker.pyint(): SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 1, 0, set(), payload), None)})
    epoll.remove({socket}, set())
    rrset, rxset = epoll.wait(timeout=0.5)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_multiple(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    local_endpoint = helper.fake_endpoint()
    endpoints = [helper.fake_endpoint() for i in range(3)]
    sockets = [helper.create_secure_connected_socket(local_endpoint, endpoints[i]) for i in range(3)]
    epoll = helper.create_epoll()
    epoll.add(set(sockets), set(sockets))

    helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(endpoints[i], local_endpoint, 1, 0, set(), payload), None) for i in range(3)
    })
    time.sleep(0.5)
    rrset, rxset = epoll.wait()
    assert rrset == set(sockets)
    assert not rxset

    sockets[0].recv(1)
    rrset, rxset = epoll.wait()
    assert rrset == set(sockets)
    assert not rxset

    sockets[0].recv(110)
    rrset, rxset = epoll.wait()
    assert rrset == {sockets[1], sockets[2]}
    assert not rxset

    sockets[0].close()
    sockets[1].close()
    rrset, rxset = epoll.wait()
    assert rrset == {sockets[1], sockets[2]}
    assert rxset == {sockets[0], sockets[1]}
