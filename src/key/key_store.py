from typing import Optional, Tuple, List
import pickle
from ..tom import Credential, Endpoint
from .encrypted_file import EncryptedFile
from .keys import Key, Keys


class KeyStore:
    __unlocked: bool = False
    __filename: str
    __master_key: str
    __keys: Keys

    def __init__(self, filename: str):
        """
        Create the key store object.

        :param filename: a path for the keystore, absolute or relative to current working directory.
        """
        self.__filename = filename

    def initialize(self, master_key: str):
        """
        Initialize the key store to empty. If the store already exists, this will discard any saved keys.

        :param master_key: the new master key of the store.
        """
        self.__check_status(False)
        self.__master_key = master_key
        self.__keys = Keys()
        self.__unlocked = True
        self.__save()

    def unlock(self, master_key: str):
        """
        Unlock the key store. The store must be initialized and locked.

        A `ValueError` will be raised if the master key is not correct.

        :param master_key: the current master key of the store.
        """
        self.__check_status(False)
        with open(self.__filename, 'rb') as f:
            serialized_keys = EncryptedFile.load(master_key.encode('utf-8'), f)
        self.__keys = pickle.loads(serialized_keys)
        self.__master_key = master_key
        self.__unlocked = True

    def lock(self):
        """
        Lock the key store.
        """
        self.__master_key = None
        self.__keys = None
        self.__unlocked = False

    def set_master_key(self, master_key):
        """
        Set the master key of the store. The store must be initialized and unlocked.

        :param master_key: the new master key to set.
        """
        self.__check_status(True)
        self.__master_key = master_key
        self.__save()

    def get_email_credential(self, protocol: str) -> Optional[Credential]:
        """
        Get email credential from the store.

        :param protocol: email protocol, e.g. smtp, imap.
        :return: a `Credential` object for the retrieved credential, or `None` if entry does not exist.
        """
        self.__check_status(True)
        return self.__keys.email.get(protocol)

    def set_email_credential(self, protocol: str, credential: Optional[Credential]):
        """
        Set email credential in the store.

        :param protocol: email protocol, e.g. smtp, imap.
        :param credential: a `Credential` object to set, or `None` to remove the entry.
        """
        self.__check_status(True)
        if credential is None:
            del self.__keys.email[protocol]
        else:
            self.__keys.email[protocol] = credential
        self.__save()

    def get_user_keys(self, type: str) -> List[Tuple[Tuple[Endpoint, Endpoint], Key]]:
        """
        Get user key list from the store.

        :param type: one of 'local' and 'remote'.
        :return: a list of endpoint pair with user keys.
        """
        self.__check_status(True)
        if type == 'local':
            keys = self.__keys.local
        elif type == 'remote':
            keys = self.__keys.remote
        else:
            raise Exception('invalid type of user keys')
        return keys

    def set_user_keys(self, type: str, keys: List[Tuple[Tuple[Endpoint, Endpoint], Key]]):
        """
        Set user key list in the store. This will overwrite all existing user keys with specified type.

        :param type: one of 'local' and 'remote'.
        :param keys: a list of endpoint pair with user keys to set.
        """
        self.__check_status(True)
        if type == 'local':
            self.__keys.local = keys
        elif type == 'remote':
            self.__keys.remote = keys
        else:
            raise Exception('invalid type of user keys')
        self.__save()

    def get_user_key(self, type: str, endpoints: Tuple[Endpoint, Endpoint]) -> Optional[Key]:
        """
        Get one user key based on endpoint pair.

        :param type: one of 'local' and 'remote'
        :param endpoints: the endpoint pair of connection
        :return: a `Key` object for user key, or `None` if not found
        """
        keys = self.get_user_keys(type)
        for key_endpoints, key in keys:
            if key_endpoints[0].matches(endpoints[0]) and key_endpoints[1].matches(endpoints[1]):
                return key
        return None

    def get_socket_context(self, endpoints: Tuple[Endpoint, Endpoint]) -> Optional[bytes]:
        """
        Get stored socket dump by endpoint pair

        :param endpoints: the endpoint pair of the dumped socket
        :return: a bytes-like object for socket dump or `None` if the dump does not exist
        """
        self.__check_status(True)
        return self.__keys.dumps.get(endpoints)

    def set_socket_context(self, endpoints: Tuple[Endpoint, Endpoint], dump: Optional[bytes]):
        """
        Store a socket dump

        :param endpoints: the endpoint pair of the dumped socket
        :param dump: a bytes-like object for socket dump, or `None` to delete the stored dump
        """
        self.__check_status(True)
        if dump is None:
            del self.__keys.dumps[endpoints]
        else:
            self.__keys.dumps[endpoints] = dump
        self.__save()

    def __save(self):
        serialized_keys = pickle.dumps(self.__keys)
        with open(self.__filename, 'wb') as f:
            EncryptedFile.dump(serialized_keys, self.__master_key.encode('utf-8'), f)

    def __check_status(self, unlocked: bool):
        if self.__unlocked != unlocked:
            raise Exception('invalid status of key store')
