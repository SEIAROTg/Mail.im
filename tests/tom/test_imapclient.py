from unittest.mock import patch, MagicMock
import socket
import pytest
from faker import Faker
from src.tom.mailbox._imapclient import IMAPClient


@pytest.fixture()
def mock_select() -> MagicMock:
    with patch('select.select') as fixture:
        yield fixture


@pytest.fixture()
def mock_imapclient() -> MagicMock:
    return MagicMock()


def test_simple(faker: Faker, mock_imapclient: MagicMock, mock_select: MagicMock):
    timeout = faker.pyfloat()
    mock_select.return_value = [mock_imapclient._sock], [], []

    def get_line_stub():
        mock_imapclient._imap._get_line.side_effect = socket.error
        return b'* 4 EXISTS'

    mock_imapclient._imap._get_line.side_effect = get_line_stub

    ret = IMAPClient.idle_check(mock_imapclient, timeout)

    assert ret == [(4, b'EXISTS')]


def test_timeout(faker: Faker, mock_imapclient: MagicMock, mock_select: MagicMock):
    timeout = faker.pyfloat()
    mock_select.return_value = [], [], []

    ret = IMAPClient.idle_check(mock_imapclient, timeout)

    assert ret == []
    mock_select.assert_called_once_with([mock_imapclient._sock], [], [], timeout)


def test_selfpipe(faker: Faker, mock_imapclient: MagicMock, mock_select: MagicMock):
    timeout = faker.pyfloat()
    selfpipe = faker.pyint()
    mock_select.return_value = [mock_imapclient._sock, selfpipe], [], []

    ret = IMAPClient.idle_check(mock_imapclient, timeout, selfpipe)

    assert ret is None
