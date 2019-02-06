import pytest
from ..socket_test_helper import SocketTestHelper
from faker import Faker
from src.tom import Endpoint
from src.tom.mailbox._packet import Packet


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_socket = helper.create_listening_socket(endpoints[1])

    thread = helper.defer(lambda: helper.feed_messages({faker.pyint(): Packet(*endpoints, 0, 0, set(), payload, is_syn=True)}), 0.5)
    socket = listening_socket.accept()
    data = socket.recv_exact(111)
    assert data == payload
    thread.join()


@pytest.mark.timeout(5)
def test_only_syn(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_socket = helper.create_listening_socket(endpoints[1])

    helper.feed_messages({faker.pyint(): Packet(*endpoints, 0, 0, set(), payload, is_syn=False)})
    socket = listening_socket.accept(0.5)
    assert socket is None


@pytest.mark.timeout(5)
def test_reply_no_syn(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_socket = helper.create_listening_socket(endpoints[0])

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload, is_syn=True)})
    socket = listening_socket.accept()
    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, {(0, 0)}, payload, is_syn=False), 0.5)


@pytest.mark.timeout(5)
def test_multiple(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    listening_socket = helper.create_listening_socket(Endpoint('', ''))

    helper.feed_messages({
        faker.pyint(): Packet(*endpoints[i], 0, 0, set(), payloads[i], is_syn=True) for i in range(3)
    })
    for i in range(3):
        socket = listening_socket.accept()
        data = socket.recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_multiple_sockets(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    listening_socket = [helper.create_listening_socket(endpoints[i][0]) for i in range(3)]

    helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints[i]), 0, 0, set(), payloads[i], is_syn=True) for i in range(3)
    })

    for i in range(3):
        socket = listening_socket[i].accept()
        data = socket.recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_timeout(helper: SocketTestHelper):
    listening_socket = helper.create_listening_socket()
    assert listening_socket.accept(timeout=0) is None


@pytest.mark.timeout(5)
def test_defer_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_socket = helper.create_listening_socket(endpoints[0])

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload, is_syn=True)})
    helper.assert_not_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5)
    socket = listening_socket.accept()
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5, 0.5)
    data = socket.recv_exact(111)
    assert data == payload
