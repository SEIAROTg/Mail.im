import pytest
from ...socket_test_helper import SocketTestHelper
from src.tom import Endpoint


def test_simple(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    listening_sockets = helper.create_listening_socket(endpoint)
    listening_sockets.close()


def test_address_in_use(helper: SocketTestHelper):
    endpoint = helper.fake_endpoint()
    listening_sockets = helper.create_listening_socket(endpoint)
    with pytest.raises(Exception) as execinfo:
        helper.create_listening_socket(Endpoint(endpoint.address, ''))
    assert execinfo.match('address already in use')


def test_invalid_status(helper: SocketTestHelper):
    listening_sockets = helper.create_listening_socket()
    with pytest.raises(Exception) as execinfo:
        listening_sockets.listen(helper.fake_endpoint())
    assert execinfo.match('invalid status of socket')
