from typing import IO
import argon2.low_level
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


class EncryptedFile:
    __ARGON2_TIME_COST: int = 16
    __ARGON2_MEMORY_COST: int = 102400
    __ARGON2_PARALLELISM: int = 8
    __ARGON2_HASH_LEN: int = 16
    __ARGON2_SALT_LEN: int = 16
    __ARGON2_TYPE: argon2.low_level.Type = argon2.low_level.Type.ID
    __ARGON2_VERSION: int = 19

    def __new__(self):
        raise RuntimeError('%s cannot not be instantiated' % self)

    @staticmethod
    def __hash_master_key(master_key: bytes, salt: bytes):
        return argon2.low_level.hash_secret_raw(
            master_key,
            salt,
            EncryptedFile.__ARGON2_TIME_COST,
            EncryptedFile.__ARGON2_MEMORY_COST,
            EncryptedFile.__ARGON2_PARALLELISM,
            EncryptedFile.__ARGON2_HASH_LEN,
            EncryptedFile.__ARGON2_TYPE,
            EncryptedFile.__ARGON2_VERSION)

    @staticmethod
    def load(master_key: bytes, f: IO[bytes]) -> bytes:
        salt = f.read(16)
        nonce = f.read(16)
        tag = f.read(16)
        ciphertext = f.read()
        key = EncryptedFile.__hash_master_key(master_key, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce)
        data = cipher.decrypt_and_verify(ciphertext, tag)
        return data

    @staticmethod
    def dump(master_key: bytes, data: bytes, f: IO[bytes]):
        salt = get_random_bytes(EncryptedFile.__ARGON2_SALT_LEN)
        key = EncryptedFile.__hash_master_key(master_key, salt)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        f.write(salt)
        f.write(cipher.nonce)
        f.write(tag)
        f.write(ciphertext)
