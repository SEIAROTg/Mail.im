from typing import Callable, Any, Tuple
from unittest.mock import patch, MagicMock
import pytest
from faker import Faker
from src.key.key_store import KeyStore
from src.tom import Endpoint


def assert_invalid_status(func: Callable[[], Any]):
    with pytest.raises(Exception) as execinfo:
        func()
    assert execinfo.match('invalid status')


def assert_valid_status(func: Callable[[], Any]):
    func()


@pytest.fixture()
def faker() -> Faker:
    return Faker()


@pytest.fixture()
def endpoints(faker: Faker) -> Tuple[Endpoint, Endpoint]:
    local_endpoint = Endpoint(faker.email(), faker.uuid4())
    remote_endpoint = Endpoint(faker.email(), faker.uuid4())
    return local_endpoint, remote_endpoint


@pytest.fixture(autouse=True)
def mock_encrypted_file() -> MagicMock:
    with patch('src.key.key_store.EncryptedFile') as fixture:
        yield fixture


@pytest.fixture(autouse=True)
def mock_open() -> MagicMock:
    with patch('src.key.key_store.open') as fixture:
        yield fixture


@pytest.fixture(autouse=True)
def mock_pickle() -> MagicMock:
    with patch('src.key.key_store.pickle') as fixture:
        yield fixture


def test_initialize(
        faker: Faker,
        mock_open: MagicMock,
        mock_encrypted_file: MagicMock,
        mock_pickle: MagicMock):
    path = faker.file_path()
    master_key = faker.password()
    store = KeyStore(path)

    store.initialize(master_key)

    mock_encrypted_file.dump.assert_called_with(
        mock_pickle.dumps.return_value,
        master_key.encode('utf-8'),
        mock_open.return_value.__enter__.return_value)

    assert_valid_status(lambda: store.get_user_keys('local'))


def test_unlock(
        faker: Faker,
        endpoints: Endpoint,
        mock_open: MagicMock,
        mock_encrypted_file: MagicMock,
        mock_pickle: MagicMock):
    path = faker.file_path()
    master_key = faker.password()
    mock_keys = mock_pickle.loads.return_value
    store = KeyStore(path)

    store.unlock(master_key)

    mock_open.assert_called_once_with(path, 'rb')
    mock_encrypted_file.load.assert_called_once_with(
        master_key.encode('utf-8'),
        mock_open.return_value.__enter__.return_value)
    mock_pickle.loads.assert_called_once_with(mock_encrypted_file.load.return_value)

    assert_valid_status(lambda: store.get_user_keys('local'))

    # keys loaded
    assert store.get_user_keys('local') == mock_keys.local

    # master key stored
    store.set_user_keys('local', [])
    mock_encrypted_file.dump.assert_called_once_with(
        mock_pickle.dumps.return_value,
        master_key.encode('utf-8'),
        mock_open.return_value.__enter__.return_value)


def test_unlock_status_change(faker: Faker):
    path = faker.file_path()
    master_key = faker.password()
    store = KeyStore(path)

    store.unlock(master_key)

    assert_invalid_status(lambda: store.initialize(master_key))
    assert_invalid_status(lambda: store.unlock(master_key))
    assert_valid_status(lambda: store.get_user_keys('local'))


def test_lock_status_change(faker: Faker):
    path = faker.file_path()
    master_key = faker.password()
    store = KeyStore(path)

    store.initialize(master_key)
    store.lock()
    assert_invalid_status(lambda: store.get_user_keys('local'))


def test_status_check_locked(faker: Faker, endpoints: Tuple[Endpoint, Endpoint]):
    path = faker.file_path()
    store = KeyStore(path)
    assert_invalid_status(lambda: store.get_email_credential('smtp'))
    assert_invalid_status(lambda: store.set_email_credential('smtp', None))
    assert_invalid_status(lambda: store.get_user_keys('local'))
    assert_invalid_status(lambda: store.set_user_keys('local', []))
    assert_invalid_status(lambda: store.get_user_key('local', endpoints))
    assert_invalid_status(lambda: store.set_master_key('key'))


def test_set_master_key(
        faker: Faker,
        mock_open: MagicMock,
        mock_encrypted_file: MagicMock,
        mock_pickle: MagicMock):
    path = faker.file_path()
    master_key = faker.password()
    store = KeyStore(path)

    store.initialize('')
    store.set_master_key(master_key)

    mock_encrypted_file.dump.assert_called_with(
        mock_pickle.dumps.return_value,
        master_key.encode('utf-8'),
        mock_open.return_value.__enter__.return_value)


def test_email_credential(faker: Faker, mock_encrypted_file: MagicMock):
    path = faker.file_path()
    smtp = MagicMock()
    imap = MagicMock()
    store = KeyStore(path)

    store.initialize('')
    store.set_email_credential('smtp', smtp)
    store.set_email_credential('imap', imap)

    assert store.get_email_credential('smtp') == smtp
    assert store.get_email_credential('imap') == imap
    assert store.get_email_credential('pop3') is None
    mock_encrypted_file.dump.assert_called()


def test_user_keys(faker: Faker, mock_encrypted_file: MagicMock):
    path = faker.file_path()
    local = MagicMock()
    remote = MagicMock()
    store = KeyStore(path)

    store.initialize('')
    store.set_user_keys('local', local)
    store.set_user_keys('remote', remote)

    assert store.get_user_keys('local') == local
    assert store.get_user_keys('remote') == remote
    with pytest.raises(Exception) as execinfo:
        assert store.get_user_keys('invalid')
    assert execinfo.match('invalid type')
    mock_encrypted_file.dump.assert_called()


def test_socket_context(faker: Faker, mock_encrypted_file: MagicMock):
    path = faker.file_path()
    store = KeyStore(path)
    dump = faker.binary(111)
    endpoints = tuple(Endpoint(faker.email(), faker.uuid4()) for _ in range(2))

    store.initialize('')
    store.set_socket_context(endpoints, dump)

    assert store.get_socket_context(endpoints) == dump
    assert store.get_socket_context(tuple(reversed(endpoints))) is None
    mock_encrypted_file.dump.assert_called()


def test_user_key(
        faker: Faker,
        mock_pickle: MagicMock,
        mock_encrypted_file: MagicMock):
    path = faker.file_path()
    mock_pickle.loads.return_value.local = [
        ((Endpoint('a', 'x'), Endpoint('b', 'y')), b'000'),
        ((Endpoint('a', 'x'), Endpoint('', '')), b'111'),
        ((Endpoint('', ''), Endpoint('b', 'y')), b'222'),
        ((Endpoint('', ''), Endpoint('', '')), b'333'),
    ]
    store = KeyStore(path)
    store.unlock('')

    assert store.get_user_key('local', (Endpoint('a', 'x'), Endpoint('b', 'y'))) == b'000'
    assert store.get_user_key('local', (Endpoint('a', 'x'), Endpoint('c', 'z'))) == b'111'
    assert store.get_user_key('local', (Endpoint('c', 'z'), Endpoint('b', 'y'))) == b'222'
    assert store.get_user_key('local', (Endpoint('c', 'z'), Endpoint('d', 'z'))) == b'333'
    assert store.get_user_key('remote', (Endpoint('a', 'x'), Endpoint('b', 'y'))) is None
