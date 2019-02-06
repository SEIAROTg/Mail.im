import pytest
from ..socket_test_helper import SocketTestHelper


def test_simple(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    socket.close()


def test_address_in_use(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        helper.create_connected_socket(*endpoints)
    assert execinfo.match('address already in use')


def test_invalid_status(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket.connect(*reversed(endpoints))
    assert execinfo.match('invalid status of socket')
