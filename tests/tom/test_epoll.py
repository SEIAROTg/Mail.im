import time
import pytest
from faker import Faker
from .socket_test_helper import SocketTestHelper
from src.tom.mailbox._packet import Packet


@pytest.fixture()
def faker() -> Faker:
    return Faker()


@pytest.fixture()
def helper() -> SocketTestHelper:
    helper = SocketTestHelper()
    yield helper
    helper.close()


def test_empty(helper: SocketTestHelper):
    socket0 = helper.create_connected_socket()
    socket1 = helper.create_connected_socket()
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
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload),
    }), 0.5)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload),
    }), 0.5)
    socket.recv(111)
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_not_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload),
    }), 0.5)
    socket.recv(1)
    rrset, rxset = epoll.wait(timeout=0)

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_order(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 1, 0, set(), payload),
    }), 0.5)
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_recv_empty_packet(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), b''),
    }), 0.5)
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_listening_socket(endpoints[0])
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload),
    }), 0.5)
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_listening_socket(endpoints[0])
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload),
    }), 0.5)
    socket.accept()
    rrset, rxset = epoll.wait(timeout=0)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_read_accept_not_reset(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    local_endpoint = helper.fake_endpoint()
    endpoints = [helper.fake_endpoint() for i in range(2)]
    socket = helper.create_listening_socket(local_endpoint)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.defer(lambda: helper.feed_messages({
        faker.pyint(): Packet(endpoints[i], local_endpoint, 0, 0, set(), payload) for i in range(2)
    }), 0.5)
    socket.accept()
    rrset, rxset = epoll.wait()

    assert rrset == {socket}
    assert not rxset


@pytest.mark.timeout(5)
def test_error_recv(faker: Faker, helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    epoll = helper.create_epoll()
    epoll.add(set(), {socket})

    helper.defer(socket.close, 0.5)
    rrset, rxset = epoll.wait()

    assert not rrset
    assert rxset == {socket}


@pytest.mark.timeout(5)
def test_error_accept(faker: Faker, helper: SocketTestHelper):
    socket = helper.create_listening_socket()
    epoll = helper.create_epoll()
    epoll.add(set(), {socket})

    helper.defer(socket.close, 0.5)
    rrset, rxset = epoll.wait()

    assert not rrset
    assert rxset == {socket}


@pytest.mark.timeout(5)
def test_remove(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    epoll = helper.create_epoll()
    epoll.add({socket}, set())

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    epoll.remove({socket}, set())
    rrset, rxset = epoll.wait(timeout=0.5)

    assert not rrset
    assert not rxset


@pytest.mark.timeout(5)
def test_multiple(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    local_endpoint = helper.fake_endpoint()
    endpoints = [helper.fake_endpoint() for i in range(3)]
    sockets = [helper.create_connected_socket(local_endpoint, endpoints[i]) for i in range(3)]
    epoll = helper.create_epoll()
    epoll.add(set(sockets), set(sockets))

    helper.feed_messages({
        faker.pyint(): Packet(endpoints[i], local_endpoint, 0, 0, set(), payload) for i in range(3)
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
