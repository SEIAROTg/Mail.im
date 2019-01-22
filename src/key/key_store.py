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
        self.__filename = filename

    def initialize(self, master_key: str):
        self.__check_status(False)
        self.__master_key = master_key
        self.__keys = Keys()
        self.__unlocked = True
        self.__save()

    def unlock(self, master_key: str):
        self.__check_status(False)
        with open(self.__filename, 'rb') as f:
            serialized_keys = EncryptedFile.load(master_key.encode('utf-8'), f)
        self.__keys = pickle.loads(serialized_keys)
        self.__master_key = master_key
        self.__unlocked = True

    def lock(self):
        self.__master_key = None
        self.__keys = None
        self.__unlocked = False

    def set_master_key(self, master_key):
        self.__check_status(True)
        self.__master_key = master_key
        self.__save()

    def get_email_credential(self, protocol: str) -> Optional[Credential]:
        self.__check_status(True)
        return self.__keys.email.get(protocol)

    def set_email_credential(self, protocol: str, credential: Optional[Credential]):
        self.__check_status(True)
        if credential is None:
            del self.__keys.email[protocol]
        else:
            self.__keys.email[protocol] = credential
        self.__save()

    def get_user_keys(self, type: str) -> List[Tuple[Tuple[Endpoint, Endpoint], Key]]:
        self.__check_status(True)
        if type == 'local':
            keys = self.__keys.local
        elif type == 'remote':
            keys = self.__keys.remote
        else:
            raise Exception('invalid type of user keys')
        return keys

    def set_user_keys(self, type: str, keys: List[Tuple[Tuple[Endpoint, Endpoint], Key]]):
        self.__check_status(True)
        if type == 'local':
            self.__keys.local = keys
        elif type == 'remote':
            self.__keys.remote = keys
        else:
            raise Exception('invalid type of user keys')
        self.__save()

    def get_user_key(self, type: str, endpoints: Tuple[Endpoint, Endpoint]) -> Optional[Key]:
        keys = self.get_user_keys(type)
        for key_endpoints, key in keys:
            if key_endpoints[0].matches(endpoints[0]) and key_endpoints[1].matches(endpoints[1]):
                return key
        return None

    def __save(self):
        serialized_keys = pickle.dumps(self.__keys)
        with open(self.__filename, 'wb') as f:
            EncryptedFile.dump(serialized_keys, self.__master_key.encode('utf-8'), f)

    def __check_status(self, unlocked: bool):
        if self.__unlocked != unlocked:
            raise Exception('invalid status of key store')
