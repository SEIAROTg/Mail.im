import time
from unittest.mock import Mock, call
import pytest
from ...socket_test_helper import SocketTestHelper
from faker import Faker
from src.tom import Endpoint
from src.tom._mailbox.packet import PlainPacket as Packet


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
    socket = listening_socket.accept(timeout=0.5)
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
def test_multiple_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111) for i in range(3)]
    listening_socket = helper.create_listening_socket(endpoints[0])

    helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints), i, 0, set(), payloads[i], is_syn=i==0) for i in range(3)
    })
    time.sleep(0.5)
    socket = listening_socket.accept()
    for i in range(3):
        data = socket.recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_multiple_connections(faker: Faker, helper: SocketTestHelper):
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


@pytest.mark.timeout(5)
def test_should_accept(faker: Faker, helper: SocketTestHelper):
    local_endpoint = helper.fake_endpoint()
    payloads = [faker.binary(111) for i in range(3)]
    remote_endpoints = [helper.fake_endpoint() for i in range(3)]
    uid = faker.pyint()
    should_accept = Mock(side_effect=[False, False, True])
    listening_socket = helper.create_listening_socket(local_endpoint)

    helper.feed_messages({
        uid+i: Packet(remote_endpoints[i], local_endpoint, 0, 0, set(), payloads[i], is_syn=True) for i in range(3)
    })
    socket = listening_socket.accept(should_accept)
    assert socket.recv_exact(111) == payloads[2]
    assert not listening_socket.accept(timeout=0)
    should_accept.assert_has_calls([
        call(local_endpoint, remote_endpoints[i], False) for i in range(3)
    ])


@pytest.mark.timeout(5)
def test_passive_restore(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages({
        uid - 1: Packet(*reversed(endpoints), 0, 0, set(), payload)
    })
    time.sleep(0.5)
    for i in range(10):
        socket.send(payload)
        helper.assert_sent(Packet(*endpoints, i, 0, {(0, 0)}, payload))
    assert socket.recv(10) == payload[:10]
    helper.feed_messages({uid: Packet(*reversed(endpoints), -1, 0, {(i, 0) for i in range(10)}, b'')})
    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 10, 0, {(0, 0)}, payload))
    time.sleep(0.5)
    socket.shutdown()
    dump = socket.dump()
    socket.close()

    listening_socket = helper.create_listening_socket(endpoints[0])
    helper.defer(lambda: helper.feed_messages({uid+1: Packet(*reversed(endpoints), 1, 0, set(), payload, is_syn=True)}), 0.5)
    socket = listening_socket.accept(lambda *args: dump)

    assert socket.recv_exact(len(payload) * 2 - 10) == (payload * 2)[10:]
    helper.assert_sent(Packet(*endpoints, 10, 1, {(1, 0)}, payload), 0.5)  # immediately retransmit


@pytest.mark.timeout(5)
def test_passive_restore_endpoints(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    endpoints2 = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_connected_socket(*endpoints)

    socket.shutdown()
    dump = socket.dump()
    socket.close()

    listening_socket = helper.create_listening_socket(endpoints2[0])
    helper.defer(lambda: helper.feed_messages({uid+1: Packet(*reversed(endpoints2), 0, 0, set(), payload, is_syn=True)}), 0.5)
    socket = listening_socket.accept(lambda *args: dump)
    socket.send(payload)

    helper.assert_sent(Packet(*endpoints2, 0, 0, {(0, 0)}, payload), 0.5)
