from __future__ import annotations
from typing import Tuple
from dataclasses import dataclass
import email.message
from email.utils import parseaddr, formataddr
from email.mime.application import MIMEApplication
from ... import Endpoint
from . import packet_pb2, PlainPacket
import doubleratchet.header
from src.crypto.doubleratchet import DoubleRatchet
import src.config


@dataclass()
class SecurePacket:
    from_: Endpoint
    to: Endpoint
    dr_header: doubleratchet.header.Header
    body: bytes
    is_syn: bool = False

    def __eq__(self, other: SecurePacket):
        return (self.from_ == other.from_
            and self.to == other.to
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
        is_syn = packet.is_syn
        dr_header = doubleratchet.header.Header(packet.dh_pub, packet.n, packet.pn)
        body = packet.body
        return cls(endpoints[0], endpoints[1], dr_header, body, is_syn)

    def to_message(self) -> email.message.Message:
        packet = self.to_pb()
        msg = MIMEApplication(packet.SerializeToString(), 'x-mailim-packet-secure', email.encoders.encode_base64)
        msg.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        msg.add_header('From', formataddr((self.from_.port, self.from_.address)))
        msg.add_header('To', formataddr((self.to.port, self.to.address)))
        return msg

    def to_pb(self):
        packet = packet_pb2.SecurePacket()
        packet.is_syn = self.is_syn
        packet.dh_pub = self.dr_header.dh_pub
        packet.n = self.dr_header.n
        packet.pn = self.dr_header.pn
        packet.body = self.body
        return packet

    @classmethod
    def encrypt(cls, plain_packet: PlainPacket, ratchet: DoubleRatchet) -> SecurePacket:
        body = plain_packet.to_pb().body
        cipher = ratchet.encryptMessage(body.SerializeToString())
        return cls(plain_packet.from_, plain_packet.to, cipher['header'], cipher['ciphertext'], plain_packet.is_syn)

    def decrypt(self, ratchet: DoubleRatchet) -> PlainPacket:
        cleartext = ratchet.decryptMessage(self.body, self.dr_header)
        packet = packet_pb2.PlainPacket()
        packet.is_syn = self.is_syn
        packet.body.ParseFromString(cleartext)
        return PlainPacket.from_pb((self.from_, self.to), packet)
