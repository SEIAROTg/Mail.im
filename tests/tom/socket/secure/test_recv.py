import pytest
from faker import Faker
from ...socket_test_helper import SocketTestHelper
import imapclient
from src.tom._mailbox.packet import PlainPacket, SecurePacket


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    plain_packet = PlainPacket(*reversed(endpoints), 1, 0, set(), payload)
    messages = {
        uid: SecurePacket.encrypt(plain_packet, None),
    }
    socket = helper.create_secure_connected_socket(*endpoints)

    helper.defer(lambda: helper.feed_messages(messages), 0.5)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload
    helper.mock_store.add_flags.assert_called_with([uid], [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_skip_plain_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: PlainPacket(*reversed(endpoints), 0, 0, set(), payload),
    }
    socket = helper.create_secure_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv(len(payload), 0.5)
    socket.close()

    assert ret == b''


@pytest.mark.timeout(5)
def test_empty_packet(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    plain_packet0 = PlainPacket(*reversed(endpoints), 1, 0, set(), b'')
    messages0 = {
        uid: SecurePacket.encrypt(plain_packet0, None),
    }
    plain_packet1 = PlainPacket(*reversed(endpoints), 2, 0, set(), payload)
    messages1 = {
        uid + 1: SecurePacket.encrypt(plain_packet1, None),
    }
    socket = helper.create_secure_connected_socket(*endpoints)

    helper.defer(lambda: helper.feed_messages(messages0), 0.5)
    helper.defer(lambda: helper.feed_messages(messages1), 1)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload


@pytest.mark.timeout(5)
def test_existing_empty_packet(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    plain_packet0 = PlainPacket(*reversed(endpoints), 1, 0, set(), b'')
    messages0 = {
        uid: SecurePacket.encrypt(plain_packet0, None),
    }
    helper.feed_messages(messages0)
    plain_packet1 = PlainPacket(*reversed(endpoints), 2, 0, set(), payload)
    messages1 = {
        uid + 1: SecurePacket.encrypt(plain_packet1, None),
    }
    socket = helper.create_secure_connected_socket(*endpoints)

    helper.defer(lambda: helper.feed_messages(messages1), 0.5)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload


@pytest.mark.timeout(5)
def test_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    uid = faker.pyint()
    plain_packet = PlainPacket(*reversed(endpoints), 1, 0, set(), payload)
    expected_response = PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0)}, b'')

    helper.feed_messages({uid: SecurePacket.encrypt(plain_packet, None)})
    helper.assert_sent(SecurePacket.encrypt(expected_response, None), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_ack_no_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    uid = faker.pyint()
    plain_packet = PlainPacket(*reversed(endpoints), 1, 0, set(), payload)
    expected_response = PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0)}, b'')

    helper.feed_messages({uid: SecurePacket.encrypt(plain_packet, None)})
    helper.assert_sent(SecurePacket.encrypt(expected_response, None), 1.5, 0.5)
    helper.assert_no_packets_sent(1.5)


@pytest.mark.timeout(5)
def test_ack_to_non_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(
        SecurePacket.encrypt(PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload), None))
    helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), 1, 0, {(1, 0)}, payload), None)})
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, -1, 0, {(1, 0)}, b''), None), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_no_ack_to_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(
        SecurePacket.encrypt(PlainPacket(*endpoints, 1, 0, {(0, 0)}, payload), None))
    helper.feed_messages({
        faker.pyint(): SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), -1, 0, {(1, 0)}, b''), None)})
    helper.assert_no_packets_sent(1.5)


@pytest.mark.timeout(5)
def test_single_ack_for_multiple_packets(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    uid = faker.pyint()
    messagess = [
        {uid + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), i + 1, 0, set(), payloads[i]), None)} for i in range(3)
    ]
    for messages in messagess:
        helper.feed_messages(messages)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0), (2, 0), (3, 0)}, b''), None), 1.5, 0.5)
    helper.assert_no_packets_sent(1.5)


@pytest.mark.timeout(5)
def test_subsequent_acks_after_compressed(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(4)]
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    uid = faker.pyint()
    messagess = [
        {uid + i: SecurePacket.encrypt(
            PlainPacket(*reversed(endpoints), i + 1, 0, set(), payloads[i]), None)} for i in range(4)
    ]
    for messages in messagess[:3]:
        helper.feed_messages(messages)

    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0), (2, 0), (3, 0)}, b''), None), 1.5, 0.5)
    helper.feed_messages(messagess[3])
    helper.assert_sent(SecurePacket.encrypt(
        PlainPacket(*endpoints, -1, 0, {(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)}, b''), None), 1.5, 0.5)
