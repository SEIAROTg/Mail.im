import pytest
from faker import Faker
from ...socket_test_helper import SocketTestHelper
from src.tom import Socket
import smtplib


@pytest.mark.timeout(5)
def test_simple(faker: Faker, helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_secure_connected_socket(*endpoints)
    socket.close()


@pytest.mark.timeout(5)
def test_timeout(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = Socket(helper.mailbox)
    smtplib.SMTP.return_value.sendmail.side_effect = lambda *args: None
    with pytest.raises(Exception) as execinfo:
        socket.connect(*endpoints, (None, None), 1)
    socket.close()
    assert execinfo.match('handshake timeout')


@pytest.mark.timeout(5)
def test_send_without_handshake(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = Socket(helper.mailbox)
    smtplib.SMTP.return_value.sendmail.side_effect = lambda *args: None
    try:
        socket.connect(*endpoints, (None, None), 0)
    except Exception:
        pass
    with pytest.raises(Exception) as execinfo:
        socket.send(b'foo')
    socket.close()
    assert execinfo.match('socket already closed')


@pytest.mark.timeout(5)
def test_address_in_use(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        helper.create_secure_connected_socket(*endpoints)
    assert execinfo.match('address already in use')


@pytest.mark.timeout(5)
def test_invalid_status(helper: SocketTestHelper):
    endpoints = helper.fake_endpoints()
    socket = helper.create_connected_socket(*endpoints)
    with pytest.raises(Exception) as execinfo:
        socket.connect(*reversed(endpoints), True)
    assert execinfo.match('invalid status of socket')
