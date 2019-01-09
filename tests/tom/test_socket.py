from typing import Tuple, Optional
import time
import threading
import imapclient
import pytest
from faker import Faker
from src.tom import Endpoint, Mailbox, Socket
from .socket_test_helper import SocketTestHelper
from src.tom.packet import Packet


@pytest.fixture()
def faker() -> Faker:
    return Faker()


@pytest.fixture()
def helper() -> SocketTestHelper:
    helper = SocketTestHelper()
    yield helper
    helper.close()


def test_connect(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.close()


def test_connect_address_in_use(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        helper.create_connected_socket(*endpoints)
    assert execinfo.match('address already in use')


def test_connect_invalid_status(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket.connect(*reversed(endpoints))
    assert execinfo.match('invalid status of socket')


def test_close_connected(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    helper.create_connected_socket(*endpoints).close()
    helper.create_connected_socket(*endpoints)


@pytest.mark.timeout(5)
def test_send(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    socket = helper.create_connected_socket(*endpoints)
    packet = Packet(*endpoints, 0, 0, set(), payload)

    socket.send(payload)
    socket.close()

    helper.assert_sent(socket, packet)


@pytest.mark.timeout(5)
def test_send_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(socket, Packet(*endpoints, 0, 0, set(), payload))
    helper.assert_sent(socket, Packet(*endpoints, 0, 1, set(), payload), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_send_no_retransmit_after_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(socket, Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, set([(0, 0)]), b'')})
    helper.assert_not_sent(socket, Packet(*endpoints, 0, 1, set(), payload), 1.5)
    helper.assert_not_sent(socket, Packet(*endpoints, 0, 1, set([-1]), payload))


@pytest.mark.timeout(5)
def test_recv(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    uid = faker.pyint()
    messages = {
        uid: Packet(*reversed(endpoints), 0, 0, set(), payload),
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv(len(payload))
    socket.close()

    assert ret == payload
    helper.mock_store.add_flags.assert_called_once_with([uid], [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_multiple_packets(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    messages = {
        uids[i]: Packet(*reversed(endpoints), i, 0, set(), payloads[i]) for i in range(3)
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv(195)
    socket.close()

    assert ret == b''.join(payloads)[:195]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_multiple_sockets(faker: Faker, helper: SocketTestHelper):
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
    ret1 = socket1.recv(111 + 53)
    ret2 = socket2.recv(36 + 1 + 71)
    socket1.close()
    socket2.close()

    assert ret1 == payloads[0] + payloads[4]
    assert ret2 == payloads[1] + payloads[2] + payloads[3]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_not_connected(faker: Faker, helper: SocketTestHelper):
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
def test_recv_invalid_packets(faker: Faker, helper: SocketTestHelper):
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
def test_recv_order(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payloads = [faker.binary(111), faker.binary(36), faker.binary(71)]
    uids = faker.pylist(3, False, int)
    seqs = [2, 0, 1]
    messages = {
        uids[i]: Packet(*reversed(endpoints), seqs[i], 0, set(), payloads[i]) for i in range(3)
    }
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages(messages)
    ret = socket.recv(218)
    socket.close()

    assert ret == payloads[1] + payloads[2] + payloads[0]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_timeout(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    socket.recv(100, timeout=0)


@pytest.mark.timeout(5)
def test_close_unblock_recv(helper: SocketTestHelper):
    socket = helper.create_connected_socket()

    def close():
        time.sleep(0.2)
        socket.close()
    thread = threading.Thread(target=close)
    thread.start()
    socket.recv(100)
    thread.join()


@pytest.mark.timeout(5)
def test_recv_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    helper.assert_sent(socket, Packet(*endpoints, -1, 0, set([(0, 0)]), b''), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_recv_ack_to_non_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(socket, Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set([(0, 0)]), payload)})
    helper.assert_sent(socket, Packet(*endpoints, -1, 0, set([(0, 0)]), b''))


@pytest.mark.timeout(5)
def test_recv_no_ack_to_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(socket, Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, set([(0, 0)]), b'')})
    helper.assert_not_sent(socket, Packet(*endpoints, -1, 0, set([(0, 0)]), b''), 1.5)
