import pytest
from unittest.mock import patch, MagicMock
import io
import argon2.low_level
from faker import Faker
from src.key.encrypted_file import EncryptedFile


@pytest.fixture()
def faker() -> Faker:
    return Faker()


@pytest.fixture()
def mock_get_random_bytes() -> MagicMock:
    with patch('src.key.encrypted_file.get_random_bytes') as fixture:
        yield fixture


@pytest.fixture()
def mock_hash_secret_raw() -> MagicMock:
    with patch('argon2.low_level.hash_secret_raw') as fixture:
        yield fixture


@pytest.fixture()
def mock_aes() -> MagicMock:
    with patch('src.key.encrypted_file.AES') as fixture:
        yield fixture


def test_dump(
        faker: Faker,
        mock_get_random_bytes: MagicMock,
        mock_hash_secret_raw: MagicMock,
        mock_aes: MagicMock):
    salt = faker.binary(16)
    master_key = faker.binary(16)
    data = faker.binary(100)
    hashed_key = faker.binary(32)
    ciphertext = faker.binary(16)
    nonce = faker.binary(16)
    tag = faker.binary(16)
    mock_get_random_bytes.return_value = salt
    mock_hash_secret_raw.return_value = hashed_key
    mock_aes.new.return_value.encrypt_and_digest.return_value = ciphertext, tag
    mock_aes.new.return_value.nonce = nonce
    stream = io.BytesIO()

    EncryptedFile.dump(master_key, data, stream)

    mock_get_random_bytes.assert_called_once_with(16)
    mock_hash_secret_raw.assert_called_once_with(master_key, salt, 16, 102400, 8, 32, argon2.low_level.Type.ID, 19)
    mock_aes.new.assert_called_once_with(hashed_key, mock_aes.MODE_GCM)
    mock_aes.new.return_value.encrypt_and_digest.assert_called_once_with(data)
    assert stream.getvalue() == salt + nonce + tag + ciphertext


def test_load(
        faker: Faker,
        mock_hash_secret_raw: MagicMock,
        mock_aes: MagicMock):
    salt = faker.binary(16)
    master_key = faker.binary(16)
    data = faker.binary(100)
    hashed_key = faker.binary(32)
    ciphertext = faker.binary(16)
    nonce = faker.binary(16)
    tag = faker.binary(16)
    mock_hash_secret_raw.return_value = hashed_key
    mock_aes.new.return_value.decrypt_and_verify.return_value = data
    stream = io.BytesIO(salt + nonce + tag + ciphertext)

    decrypted_data = EncryptedFile.load(master_key, stream)

    mock_hash_secret_raw.assert_called_once_with(master_key, salt, 16, 102400, 8, 32, argon2.low_level.Type.ID, 19)
    mock_aes.new.assert_called_once_with(hashed_key, mock_aes.MODE_GCM, nonce)
    mock_aes.new.return_value.decrypt_and_verify.assert_called_once_with(ciphertext, tag)
    assert decrypted_data == data


def test_load_dump(faker: Faker):
    master_key = faker.binary(16)
    data = faker.binary(100)
    stream = io.BytesIO()

    EncryptedFile.dump(master_key, data, stream)
    stream = io.BytesIO(stream.getvalue())
    decrypted_data = EncryptedFile.load(master_key, stream)

    assert decrypted_data == data
