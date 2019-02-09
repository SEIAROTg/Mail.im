from __future__ import annotations
from typing import Optional
import doubleratchet
import nacl.public
import nacl.bindings.crypto_scalarmult
import src.config


class SendReceiveChain(doubleratchet.kdfchains.ConstKDFChain):
    def __init__(self, key):
        root_key_kdf = doubleratchet.recommended.RootKeyKDF('SHA-512', b'mailim-send-receive-chain')
        const_key = b'\xbfu\xa9\x03\xfc\xa4\xfc4\xe1\xa9\x85/Y\xc4\x9d\x84\xc9\x9e\xeb\r\xd16\xc5W\x9f\xa3 \xa6\x1dd\xfduM\xa3\x1a\xba\xab\xa9\x08\x8dEM\x92E\x1a\x83\xa3\x11\x91\xab\xf2{\xfc^\xd0B\x15%I\x84\xe7\xd6\x9a\xba'
        super().__init__(const_key, root_key_kdf, key)


class SymmetricKeyRatchet(doubleratchet.ratchets.SymmetricKeyRatchet):
    def __init__(self):
        super().__init__(SendReceiveChain, SendReceiveChain)


class RootChain(doubleratchet.kdfchains.KDFChain):
    def __init__(self):
        root_key_kdf = doubleratchet.recommended.RootKeyKDF('SHA-512', b'mailim-root-chain')
        init_key = b'\xc6\x19\xfb\xad\xd07\x83\x9d(R\xaf\xe8\xc0\xa2\xde\xf4\xd4 D\xa4\xd6r~f\xad\x86G\xc9\x8fI.\xaa\xed\xdb\x8d\xd3\x02]\xad+\x1e\x9c}\xa4\x04M\x95\xbd\xaf\xdd\xbbQ9\xceL\xac!Y_\x03\xe4D\x89t'
        super().__init__(root_key_kdf, init_key)


class DoubleRatchet(doubleratchet.ratchets.DoubleRatchet):
    def __init__(self, own_key: Optional[bytes] = None, other_pub: Optional[bytes] = None):
        aead = doubleratchet.recommended.CBCHMACAEAD('SHA-512', b'mailim-hmac')
        super().__init__(
            aead,
            src.config.config['crypto']['MaxMsgKeys'],
            SymmetricKeyRatchet(),
            b'mailim-packet-data',
            KeyPair,
            RootChain(),
            own_key,
            other_pub)

    def _makeAD(self, header, ad):
        return ad


class KeyPair(doubleratchet.KeyPair):
    __priv: Optional[nacl.public.PrivateKey] = None
    __pub: Optional[nacl.public.PublicKey] = None

    def __init__(self, priv: Optional[bytes] = None, pub : Optional[bytes] = None):
        if priv is not None:
            self.__priv = nacl.public.PrivateKey(priv)
            self.__pub = self.__priv.public_key
        elif pub is not None:
            self.__pub = nacl.public.PublicKey(pub)

    @classmethod
    def generate(cls):
        priv = nacl.public.PrivateKey.generate()
        self = cls()
        self.__priv = priv
        self.__pub = priv.public_key
        return self

    def serialize(self):
        return (
            super().serialize(),
            bytes(self.__priv) if self.__priv is not None else None,
            bytes(self.__pub) if self.__pub is not None else None,
        )

    @classmethod
    def fromSerialized(cls, serialized, *args, **kwargs):
        self = super().fromSerialized(serialized[0], *args, **kwargs)
        cls.__init__(self, serialized[1], serialized[2])
        return self

    @property
    def pub(self) -> Optional[bytes]:
        return self.__pub and bytes(self.__pub)

    @property
    def priv(self) -> Optional[bytes]:
        return self.__priv and bytes(self.__priv)

    def getSharedSecret(self, other: KeyPair):
        if self.priv is None or other.pub is None:
            raise doubleratchet.exceptions.MissingKeyException()
        return nacl.bindings.crypto_scalarmult(self.priv, other.pub)
