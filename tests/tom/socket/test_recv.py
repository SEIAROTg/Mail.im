import pytest
from ..socket_test_helper import SocketTestHelper
from faker import Faker
from unittest.mock import call
import imapclient
import time
from src.tom import Endpoint
from src.tom._mailbox.packet import PlainPacket as Packet


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), payload),
    }
    socket = helper.create_connected_socket(*endpoints)

    thread = helper.defer(lambda: helper.feed_messages(messages), 0.5)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload
    helper.mock_store.add_flags.assert_called_once_with([uid], [imapclient.SEEN])
    thread.join()


@pytest.mark.timeout(5)
def test_empty_packet(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages0 = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), b''),
    }
    messages1 = {
        uid + 1: Packet(*reversed(endpoints), 1, 0, set(), payload),
    }
    socket = helper.create_connected_socket(*endpoints)

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
    messages0 = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), b''),
    }
    helper.feed_messages(messages0)
    messages1 = {
        uid + 1: Packet(*reversed(endpoints), 1, 0, set(), payload),
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.defer(lambda: helper.feed_messages(messages1), 0.5)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload


@pytest.mark.timeout(5)
def test_not_block(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), payload),
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv(len(payload) * 10)
    socket.close()

    assert ret == payload
    helper.mock_store.add_flags.assert_called_once_with([uid], [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_multiple_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    messages = {
        uids[i]: Packet(*reversed(endpoints), i, 0, set(), payloads[i]) for i in range(3)
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    time.sleep(0.5)
    ret = socket.recv(195)
    socket.close()

    assert ret == b''.join(payloads)[:195]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_exact(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111) for _ in range(2)]
    uid = faker.pyint()
    messagess = [
        {uid + i: Packet(*reversed(endpoints), i, 0, set(), payloads[i])} for i in range(2)
    ]
    socket = helper.create_connected_socket(*endpoints)

    thread0 = helper.defer(lambda: helper.feed_messages(messagess[0]), 0.5)
    thread1 = helper.defer(lambda: helper.feed_messages(messagess[1]), 1)
    ret = socket.recv_exact(sum(map(len, payloads)))
    socket.close()

    assert ret == b''.join(payloads)
    helper.mock_store.add_flags.assert_has_calls([
        call([uid + i], [imapclient.SEEN]) for i in range(2)
    ])
    thread0.join()
    thread1.join()


@pytest.mark.timeout(5)
def test_exact_multiple_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    messages = {
        uids[i]: Packet(*reversed(endpoints), i, 0, set(), payloads[i]) for i in range(3)
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv_exact(195)
    socket.close()

    assert ret == b''.join(payloads)[:195]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_multiple_sockets(faker: Faker, helper: SocketTestHelper):
    endpoints1 = helper.fake_endpoints()
    endpoints2 = (Endpoint(endpoints1[0].address, '!' + endpoints1[0].port), endpoints1[1])
    payloads = [faker.binary(111), faker.binary(36), faker.binary(1), faker.binary(71), faker.binary(53)]
    uids = faker.pylist(5, False, int)
    seqs = [0, 0, 1, 2, 1]
    targets = [endpoints1, endpoints2, endpoints2, endpoints2, endpoints1]
    messages = {
        uids[i]: Packet(*reversed(targets[i]), seqs[i], 0, set(), payloads[i]) for i in range(5)
    }
    socket1 = helper.create_connected_socket(*endpoints1)
    socket2 = helper.create_connected_socket(*endpoints2)

    helper.feed_messages(messages)
    ret1 = socket1.recv_exact(111 + 53)
    ret2 = socket2.recv_exact(36 + 1 + 71)
    socket1.close()
    socket2.close()

    assert ret1 == payloads[0] + payloads[4]
    assert ret2 == payloads[1] + payloads[2] + payloads[3]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_not_connected(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), payload),
    }

    helper.feed_messages(messages)
    helper.close()

    helper.mock_store.add_flags.assert_not_called()


@pytest.mark.timeout(5)
def test_invalid_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), payload),
    }
    helper.mock_packet.from_message.side_effect = Exception('invalid packet')

    helper.feed_messages(messages)
    helper.close()

    helper.mock_store.add_flags.assert_not_called()


@pytest.mark.timeout(5)
def test_order(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    seqs = [2, 0, 1]
    messages = {
        uids[i]: Packet(*reversed(endpoints), seqs[i], 0, set(), payloads[i]) for i in range(3)
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv_exact(218)
    socket.close()

    assert ret == payloads[1] + payloads[2] + payloads[0]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_timeout(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    socket.recv(100, timeout=0)


@pytest.mark.timeout(5)
def test_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_ack_to_non_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, {(0, 0)}, payload, is_syn=False)})
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b'', is_syn=False))


@pytest.mark.timeout(5)
def test_no_ack_to_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload, is_syn=True))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, {(0, 0)}, b'', is_syn=False)})
    helper.assert_not_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b'', is_syn=False), 1.5)
