from __future__ import annotations
from typing import Tuple, Set
from dataclasses import dataclass
import email.message
from email.utils import parseaddr, formataddr
from email.mime.application import MIMEApplication
import Crypto.Random
from xeddsa.xeddsa import XEdDSA
from ... import Endpoint
from . import packet_pb2, Packet, PlainPacket
import doubleratchet.header
from src.crypto.doubleratchet import DoubleRatchet
import src.config


@dataclass()
class SecurePacket(Packet):
    acks: Set[Tuple[int, int]]  # {(seq, attempt)}
    dr_header: doubleratchet.header.Header
    signature: bytes
    body: bytes
    is_syn: bool = False

    def __eq__(self, other: SecurePacket):
        return (super().__eq__(other)
                and self.acks == other.acks
                and self.dr_header.dh_pub == self.dr_header.dh_pub
                and self.dr_header.n == self.dr_header.n
                and self.dr_header.pn == self.dr_header.pn
                and self.signature == other.signature
                and self.body == other.body
                and self.is_syn == other.is_syn)

    @classmethod
    def from_message(cls, msg: email.message.Message) -> SecurePacket:
        if msg.get('X-Mailer') != src.config.config['tom']['X-Mailer']:
            raise Exception('invalid packet: invalid X-Mailer header')
        if msg.get_content_type() != 'application/x-mailim-packet-secure':
            raise Exception('invalid packet: invalid Content-Type header')
        packet = packet_pb2.SecurePacket()
        packet.ParseFromString(msg.get_payload(decode=True))
        from_ = Endpoint(*reversed(parseaddr(msg.get('From'))))
        to = Endpoint(*reversed(parseaddr(msg.get('To'))))
        return cls.from_pb((from_, to), packet)

    @classmethod
    def from_pb(cls, endpoints: Tuple[Endpoint, Endpoint], packet: packet_pb2.SecurePacket) -> SecurePacket:
        is_syn = packet.header.is_syn
        acks = set((id.seq, id.attempt) for id in packet.header.acks)
        dh_pub = packet.header.dh_pub
        n = packet.header.n
        pn = packet.header.pn if packet.header.pn != -1 else None
        dr_header = doubleratchet.header.Header(dh_pub, n, pn)
        signature = packet.header.signature
        body = packet.body
        return cls(endpoints[0], endpoints[1], acks, dr_header, signature, body, is_syn)

    def to_message(self) -> email.message.Message:
        packet = self.to_pb()
        msg = MIMEApplication(packet.SerializeToString(), 'x-mailim-packet-secure', email.encoders.encode_base64)
        msg.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        msg.add_header('From', formataddr((self.from_.port, self.from_.address)))
        msg.add_header('To', formataddr((self.to.port, self.to.address)))
        return msg

    def __to_pb_header(self):
        header = packet_pb2.SecurePacketHeader()
        header.is_syn = self.is_syn
        acks = []
        for seq, attempt in self.acks:
            id = packet_pb2.PacketId()
            id.seq = seq
            id.attempt = attempt
            acks.append(id)
        header.acks.extend(acks)
        header.dh_pub = self.dr_header.dh_pub
        header.n = self.dr_header.n
        header.pn = self.dr_header.pn if self.dr_header.pn is not None else -1
        header.signature = self.signature
        return header

    @staticmethod
    def __plain_to_pb_body(packet: PlainPacket):
        body = packet_pb2.SecurePacketBody()
        body.id.seq = packet.seq
        body.id.attempt = 0
        body.payload = packet.payload
        body.obfuscation = Crypto.Random.get_random_bytes(4000 - len(packet.payload) % 4000)
        return body

    def to_pb(self):
        packet = packet_pb2.SecurePacket()
        packet.header.CopyFrom(self.__to_pb_header())
        packet.body = self.body
        return packet

    @classmethod
    def encrypt(cls, plain_packet: PlainPacket, ratchet: DoubleRatchet, xeddsa: XEdDSA) -> SecurePacket:
        if plain_packet.seq == -1:  # pure ack
            header = doubleratchet.header.Header(None, 0, 0)
            return cls(plain_packet.from_, plain_packet.to, set(plain_packet.acks), header, b'', plain_packet.is_syn)
        if plain_packet.seq == 0 and plain_packet.is_syn:  # handshake
            body = None
            cipher = {
                'header': doubleratchet.header.Header(ratchet.pub, 0, 0),
                'ciphertext': b'',
            }
        else:
            body = cls.__plain_to_pb_body(plain_packet)
            cipher = ratchet.encryptMessage(body.SerializeToString())
        self = cls(
            plain_packet.from_,
            plain_packet.to,
            set(plain_packet.acks),
            cipher['header'],
            b'',
            cipher['ciphertext'],
            plain_packet.is_syn)

        signed_part = packet_pb2.SecurePacketSignedPart()
        signed_part.header.CopyFrom(self.__to_pb_header())
        if body is not None:
            signed_part.body.CopyFrom(body)
        nonce = Crypto.Random.get_random_bytes(64)
        signature = xeddsa.sign(signed_part.SerializeToString(), nonce)
        self.signature = signature
        return self

    def decrypt(self, ratchet: DoubleRatchet, xeddsa: XEdDSA) -> PlainPacket:
        if self.body == b'' and self.dr_header.dh_pub is None:  # pure ack
            return PlainPacket(self.from_, self.to, -1, 0, set(self.acks), b'', self.is_syn)
        if self.body == b'' and self.is_syn:  # handshake
            body = None
        else:
            cleartext = ratchet.decryptMessage(self.body, self.dr_header)
            body = packet_pb2.SecurePacketBody()
            body.ParseFromString(cleartext)

        header = self.__to_pb_header()
        header.signature = b''

        signed_part = packet_pb2.SecurePacketSignedPart()
        signed_part.header.CopyFrom(header)
        if body is not None:
            signed_part.body.CopyFrom(body)
        if not xeddsa.verify(signed_part.SerializeToString(), self.signature):
            raise Exception('invalid signature')

        if body is None:
            seq = 0
            payload = b''
        else:
            seq = body.id.seq
            payload = body.payload
        return PlainPacket(self.from_, self.to, seq, 0, set(self.acks), payload, self.is_syn)

