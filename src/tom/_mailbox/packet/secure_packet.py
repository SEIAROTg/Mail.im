from __future__ import annotations
from typing import Tuple, Set
from dataclasses import dataclass
import email.message
from email.utils import parseaddr, formataddr
from email.mime.application import MIMEApplication
from ... import Endpoint
from . import packet_pb2, Packet, PlainPacket
import doubleratchet.header
from src.crypto.doubleratchet import DoubleRatchet
import src.config


@dataclass()
class SecurePacket(Packet):
    acks: Set[Tuple[int, int]]  # {(seq, attempt)}
    dr_header: doubleratchet.header.Header
    body: bytes
    is_syn: bool = False

    def __eq__(self, other: SecurePacket):
        return (super().__eq__(other)
                and self.acks == other.acks
                and self.dr_header.dh_pub == self.dr_header.dh_pub
                and self.dr_header.n == self.dr_header.n
                and self.dr_header.pn == self.dr_header.pn
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
        body = packet.body
        return cls(endpoints[0], endpoints[1], acks, dr_header, body, is_syn)

    def to_message(self) -> email.message.Message:
        packet = self.to_pb()
        msg = MIMEApplication(packet.SerializeToString(), 'x-mailim-packet-secure', email.encoders.encode_base64)
        msg.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        msg.add_header('From', formataddr((self.from_.port, self.from_.address)))
        msg.add_header('To', formataddr((self.to.port, self.to.address)))
        return msg

    def to_pb(self):
        packet = packet_pb2.SecurePacket()
        packet.header.is_syn = self.is_syn
        acks = []
        for seq, attempt in self.acks:
            id = packet_pb2.PacketId()
            id.seq = seq
            id.attempt = attempt
            acks.append(id)
        packet.header.acks.extend(acks)
        packet.header.dh_pub = self.dr_header.dh_pub
        packet.header.n = self.dr_header.n
        packet.header.pn = self.dr_header.pn if self.dr_header.pn is not None else -1
        packet.body = self.body
        return packet

    @classmethod
    def encrypt(cls, plain_packet: PlainPacket, ratchet: DoubleRatchet) -> SecurePacket:
        if plain_packet.seq == -1:
            header = doubleratchet.header.Header(None, 0, 0)
            return cls(plain_packet.from_, plain_packet.to, set(plain_packet.acks), header, b'', plain_packet.is_syn)
        body = plain_packet.to_pb().body
        cipher = ratchet.encryptMessage(body.SerializeToString())
        return cls(
            plain_packet.from_,
            plain_packet.to,
            set(plain_packet.acks),
            cipher['header'],
            cipher['ciphertext'],
            plain_packet.is_syn)

    def decrypt(self, ratchet: DoubleRatchet) -> PlainPacket:
        if not self.body:
            return PlainPacket(self.from_, self.to, -1, 0, set(self.acks), b'', self.is_syn)
        cleartext = ratchet.decryptMessage(self.body, self.dr_header)
        packet = packet_pb2.PlainPacket()
        packet.body.ParseFromString(cleartext)
        plain_packet = PlainPacket.from_pb((self.from_, self.to), packet)
        plain_packet.is_syn = self.is_syn
        plain_packet.acks = set(self.acks)
        return plain_packet
