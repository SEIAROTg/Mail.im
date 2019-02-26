from __future__ import annotations
from typing import Set, Tuple
from dataclasses import dataclass
import email.message
from email.utils import parseaddr, formataddr
from email.mime.application import MIMEApplication
from ... import Endpoint
from . import packet_pb2, Packet
import src.config


@dataclass()
class PlainPacket(Packet):
    from_: Endpoint
    to: Endpoint
    seq: int
    attempt: int
    acks: Set[Tuple[int, int]]           # {(seq, attempt)}
    payload: bytes
    is_syn: bool = False

    @classmethod
    def from_message(cls, msg: email.message.Message) -> PlainPacket:
        if msg.get('X-Mailer') != src.config.config['tom']['X-Mailer']:
            raise Exception('invalid packet: invalid X-Mailer header')
        if msg.get_content_type() != 'application/x-mailim-packet':
            raise Exception('invalid packet: invalid Content-Type header')
        from_ = Endpoint(*reversed(parseaddr(msg.get('From'))))
        to = Endpoint(*reversed(parseaddr(msg.get('To'))))
        packet = packet_pb2.PlainPacket()
        packet.ParseFromString(msg.get_payload(decode=True))
        return cls.from_pb((from_, to), packet)

    @classmethod
    def from_pb(cls, endpoints: Tuple[Endpoint, Endpoint],  packet: packet_pb2.PlainPacket) -> PlainPacket:
        is_syn = packet.header.is_syn
        acks = set((id.seq, id.attempt) for id in packet.header.acks)
        seq = packet.body.id.seq
        attempt = packet.body.id.attempt
        payload = packet.body.payload
        return cls(endpoints[0], endpoints[1], seq, attempt, acks, payload, is_syn)

    def to_message(self) -> email.message.Message:
        packet = self.to_pb()
        msg = MIMEApplication(packet.SerializeToString(), 'x-mailim-packet', email.encoders.encode_base64)
        msg.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        msg.add_header('From', formataddr((self.from_.port, self.from_.address)))
        msg.add_header('To', formataddr((self.to.port, self.to.address)))
        return msg

    def to_pb(self) -> packet_pb2.PlainPacket:
        packet = packet_pb2.PlainPacket()
        packet.header.is_syn = self.is_syn
        acks = []
        for seq, attempt in self.acks:
            id = packet_pb2.PacketId()
            id.seq = seq
            id.attempt = attempt
            acks.append(id)
        packet.header.acks.extend(acks)
        packet.body.id.seq = self.seq
        packet.body.id.attempt = self.attempt
        packet.body.payload = self.payload
        return packet
