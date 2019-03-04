from unittest.mock import Mock, call
import time
import pytest
from ...socket_test_helper import SocketTestHelper
from faker import Faker
from src.tom import Endpoint
from src.tom._mailbox.packet import PlainPacket, SecurePacket


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    listening_socket = helper.create_listening_socket(endpoints[0])

    handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=True), None)
    handshake_packet.body = b''
    helper.feed_messages({uid: handshake_packet})
    socket = listening_socket.accept()
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 0, 0, set(), b''), None))
    helper.feed_messages({uid + 1: SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 1, 0, {(0, 0)}, payload), None)})
    data = socket.recv_exact(111)
    assert data == payload


@pytest.mark.timeout(5)
def test_only_syn(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    listening_socket = helper.create_listening_socket(endpoints[1])

    handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=False), None)
    handshake_packet.body = b''
    helper.feed_messages({uid: handshake_packet})
    socket = listening_socket.accept(timeout=0.5)
    assert socket is None


@pytest.mark.timeout(5)
def test_reply_no_syn(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    listening_socket = helper.create_listening_socket(endpoints[0])

    handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=True), None)
    handshake_packet.body = b''
    helper.feed_messages({uid: handshake_packet})

    socket = listening_socket.accept()
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 0, 0, set(), b'', is_syn=False), None), 0.5)
    socket.send(payload)
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 1, 0, set(), payload, is_syn=False), None), 0.5)


@pytest.mark.timeout(5)
def test_multiple_connections(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    uid = faker.pyint()
    listening_socket = helper.create_listening_socket(Endpoint('', ''))

    handshake_packets = {}
    for i in range(3):
        handshake_packet = SecurePacket.encrypt(PlainPacket(*endpoints[i], 0, 0, set(), b'', is_syn=True), None)
        handshake_packet.body = b''
        handshake_packets[uid + i] = handshake_packet
    helper.feed_messages(handshake_packets)
    sockets = [listening_socket.accept() for i in range(3)]
    helper.feed_messages({
        uid + 1000 + i: SecurePacket.encrypt(
            PlainPacket(*endpoints[i], 1, 0, set(), payloads[i]), None) for i in range(3)})

    for i in range(3):
        data = sockets[i].recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_multiple_sockets(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    uid = faker.pyint()
    listening_socket = [helper.create_listening_socket(endpoints[i][0]) for i in range(3)]

    handshake_packets = {}
    for i in range(3):
        handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints[i]), 0, 0, set(), b'', is_syn=True), None)
        handshake_packet.body = b''
        handshake_packets[uid + i] = handshake_packet
    helper.feed_messages(handshake_packets)
    sockets = [listening_socket[i].accept() for i in range(3)]
    helper.feed_messages({
        uid + 1000 + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints[i]), 1, 0, set(), payloads[i]), None) for i in range(3)})

    for i in range(3):
        data = sockets[i].recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_defer_handshake_response(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    listening_socket = helper.create_listening_socket(endpoints[0])

    handshake_packet = SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 0, 0, set(), b'', is_syn=True), None)
    handshake_packet.body = b''
    helper.feed_messages({uid: handshake_packet})
    helper.assert_no_packets_sent(1.5)
    socket = listening_socket.accept()
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 0, 0, set(), b''), None), 0.5)


@pytest.mark.timeout(5)
def test_should_accept(faker: Faker, helper: SocketTestHelper):
    local_endpoint = helper.fake_endpoint()
    payload = faker.binary(111)
    remote_endpoints = [helper.fake_endpoint() for i in range(3)]
    uid = faker.pyint()
    should_accept = Mock(side_effect=[False, False, True])
    listening_socket = helper.create_listening_socket(local_endpoint)

    handshake_packets = {}
    for i in range(3):
        handshake_packet = SecurePacket.encrypt(
            PlainPacket(remote_endpoints[i], local_endpoint, 0, 0, set(), b'', is_syn=True), None)
        handshake_packet.body = b''
        handshake_packets[uid + i] = handshake_packet
    helper.feed_messages(handshake_packets)
    socket = listening_socket.accept(should_accept)
    helper.feed_messages({
        uid + 1000: SecurePacket.encrypt(
            PlainPacket(remote_endpoints[2], local_endpoint, 1, 0, set(), payload), None)})
    assert socket.recv_exact(111) == payload
    assert not listening_socket.accept(timeout=0)
    should_accept.assert_has_calls([
        call(local_endpoint, remote_endpoints[i], True) for i in range(3)
    ])


@pytest.mark.timeout(5)
def test_passive_restore(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_secure_connected_socket(*endpoints)

    helper.feed_messages({
        uid - 1: SecurePacket.encrypt(PlainPacket(*reversed(endpoints), 1, 0, set(), payload), None)
    })
    time.sleep(0.5)
    for i in range(10):
        socket.send(payload)
        helper.assert_sent(SecurePacket.encrypt(PlainPacket(*endpoints, i + 1, 0, {(0, 0), (1, 0)}, payload), None))
    assert socket.recv(10) == payload[:10]
    helper.feed_messages({uid: SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), -1, 0, {(i, 0) for i in range(11)}, b''), None)})
    socket.send(payload)
    helper.assert_sent(SecurePacket.encrypt(PlainPacket(*endpoints, 11, 0, {(0, 0), (1, 0)}, payload), None))
    time.sleep(0.5)
    socket.shutdown()
    dump = socket.dump()
    socket.close()

    listening_socket = helper.create_listening_socket(endpoints[0])
    helper.defer(lambda: helper.feed_messages({uid+1: SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints), 2, 0, set(), payload, is_syn=True), None)}), 0.5)
    socket = listening_socket.accept(lambda *args: dump)

    assert socket.recv_exact(len(payload) * 2 - 10) == (payload * 2)[10:]
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, 11, 0, {(0, 0), (1, 0)}, payload), None), 0.5)  # immediately retransmit


@pytest.mark.timeout(5)
def test_passive_restore_endpoints(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    endpoints2 = helper.fake_endpoints()
    uid = faker.pyint()
    socket = helper.create_secure_connected_socket(*endpoints)

    socket.shutdown()
    dump = socket.dump()
    socket.close()

    listening_socket = helper.create_listening_socket(endpoints2[0])
    helper.defer(lambda:helper.feed_messages({uid+1: SecurePacket.encrypt(
        PlainPacket(*reversed(endpoints2), 1, 0, set(), payload, is_syn=True), None)}), 0.5)
    socket = listening_socket.accept(lambda *args: dump)
    socket.send(payload)

    helper.assert_sent(SecurePacket.encrypt(PlainPacket(*endpoints2, 1, 0, {(0, 0), (1, 0)}, payload), None), 0.5)
