import time
from unittest.mock import call
import imapclient
import pytest
from faker import Faker
from src.tom import Endpoint
from .socket_test_helper import SocketTestHelper
from src.tom.mailbox._packet import Packet


@pytest.fixture()
def helper() -> SocketTestHelper:
    helper = SocketTestHelper()
    yield helper
    helper.close()


# connect


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


# listen


def test_listen(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    listening_sockets = helper.create_listening_socket(endpoint)
    listening_sockets.close()


def test_listen_address_in_use(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    listening_sockets = helper.create_listening_socket(endpoint)
    with pytest.raises(Exception) as execinfo:
        helper.create_listening_socket(Endpoint(endpoint.address, ''))
    assert execinfo.match('address already in use')


def test_listen_invalid_status(helper: SocketTestHelper):
    listening_sockets = helper.create_listening_socket()
    with pytest.raises(Exception) as execinfo:
        listening_sockets.listen(helper.fake_endpoint())
    assert execinfo.match('invalid status of socket')


# accept

@pytest.mark.timeout(5)
def test_accept(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_socket = helper.create_listening_socket(endpoints[1])

    thread = helper.defer(lambda: helper.feed_messages({faker.pyint(): Packet(*endpoints, 0, 0, set(), payload)}), 0.5)
    socket = listening_socket.accept()
    data = socket.recv_exact(111)
    assert data == payload
    thread.join()


@pytest.mark.timeout(5)
def test_accept_multiple(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    listening_socket = helper.create_listening_socket(Endpoint('', ''))

    helper.feed_messages({
        faker.pyint(): Packet(*endpoints[i], 0, 0, set(), payloads[i]) for i in range(3)
    })
    for i in range(3):
        socket = listening_socket.accept()
        data = socket.recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_accept_multiple_sockets(faker: Faker, helper: SocketTestHelper):
    payloads = [faker.binary(111) for i in range(3)]
    endpoints = [helper.fake_endpoints() for i in range(3)]
    listening_sockets = [helper.create_listening_socket(endpoints[i][0]) for i in range(3)]

    helper.feed_messages({
        faker.pyint(): Packet(*reversed(endpoints[i]), 0, 0, set(), payloads[i]) for i in range(3)
    })

    for i in range(3):
        socket = listening_sockets[i].accept()
        data = socket.recv_exact(111)
        assert data == payloads[i]


@pytest.mark.timeout(5)
def test_accept_timeout(helper: SocketTestHelper):
    listening_sockets = helper.create_listening_socket()
    assert listening_sockets.accept(timeout=0) is None


@pytest.mark.timeout(5)
def test_accept_defer_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    listening_sockets = helper.create_listening_socket(endpoints[0])

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    helper.assert_not_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5)
    socket = listening_sockets.accept()
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5, 0.5)
    data = socket.recv_exact(111)
    assert data == payload


# close


def test_close_connected(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    helper.create_connected_socket(*endpoints).close()
    helper.create_connected_socket(*endpoints)


def test_close_listening(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    helper.create_listening_socket(endpoint).close()
    helper.create_listening_socket(endpoint)


@pytest.mark.timeout(5)
def test_close_unblock_recv(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.recv_exact(100)
    assert execinfo.match('already closed')
    thread.join()


@pytest.mark.timeout(5)
def test_close_unblock_accept(helper: SocketTestHelper):
    socket = helper.create_listening_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.accept()
    assert execinfo.match('already closed')
    thread.join()


# send


@pytest.mark.timeout(5)
def test_send(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    payload = faker.binary(111)
    socket = helper.create_connected_socket(*endpoints)
    packet = Packet(*endpoints, 0, 0, set(), payload)

    socket.send(payload)
    socket.close()

    helper.assert_sent(packet)


@pytest.mark.timeout(5)
def test_send_retransmit(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload))
    helper.assert_sent(Packet(*endpoints, 0, 1, set(), payload), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_send_no_retransmit_after_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, {(0, 0)}, b'')})
    helper.assert_not_sent(Packet(*endpoints, 0, 1, set(), payload), 1.5)
    helper.assert_not_sent(Packet(*endpoints, 0, 1, {(-1, 0)}, payload))


# recv

@pytest.mark.timeout(5)
def test_recv(faker: Faker, helper: SocketTestHelper):
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
def test_recv_not_block(faker: Faker, helper: SocketTestHelper):
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
def test_recv_multiple_packets(faker: Faker, helper: SocketTestHelper):
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
def test_recv_exact(faker: Faker, helper: SocketTestHelper):
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
def test_recv_exact_multiple_packets(faker: Faker, helper: SocketTestHelper):
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
    ret1 = socket1.recv_exact(111 + 53)
    ret2 = socket2.recv_exact(36 + 1 + 71)
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
    ret = socket.recv_exact(218)
    socket.close()

    assert ret == payloads[1] + payloads[2] + payloads[0]
    helper.mock_store.add_flags.assert_called_once_with(uids, [imapclient.SEEN])


@pytest.mark.timeout(5)
def test_recv_timeout(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    socket.recv(100, timeout=0)


@pytest.mark.timeout(5)
def test_recv_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, set(), payload)})
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5, 0.5)


@pytest.mark.timeout(5)
def test_recv_ack_to_non_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), 0, 0, {(0, 0)}, payload)})
    helper.assert_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''))


@pytest.mark.timeout(5)
def test_recv_no_ack_to_pure_ack(faker: Faker, helper: SocketTestHelper):
    payload = faker.binary(111)
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)

    socket.send(payload)
    helper.assert_sent(Packet(*endpoints, 0, 0, set(), payload))
    helper.feed_messages({faker.pyint(): Packet(*reversed(endpoints), -1, 0, {(0, 0)}, b'')})
    helper.assert_not_sent(Packet(*endpoints, -1, 0, {(0, 0)}, b''), 1.5)
