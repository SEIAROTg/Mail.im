import pytest
from ..socket_test_helper import SocketTestHelper


def test_connected(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    helper.create_connected_socket(*endpoints).close()
    helper.create_connected_socket(*endpoints)


def test_listening(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    helper.create_listening_socket(endpoint).close()
    helper.create_listening_socket(endpoint)


@pytest.mark.timeout(5)
def test_unblock_recv(helper: SocketTestHelper):
    socket = helper.create_connected_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.recv_exact(100)
    assert execinfo.match('already closed')
    thread.join()


@pytest.mark.timeout(5)
def test_unblock_accept(helper: SocketTestHelper):
    socket = helper.create_listening_socket()
    thread = helper.defer(socket.close, 0.2)
    with pytest.raises(Exception) as execinfo:
        socket.accept()
    assert execinfo.match('already closed')
    thread.join()
