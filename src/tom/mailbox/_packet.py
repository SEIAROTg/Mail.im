from __future__ import annotations
from typing import Set, Tuple
import email.message
import email.encoders
from email.utils import parseaddr, formataddr
from email.mime.application import MIMEApplication
from dataclasses import dataclass
from .. import Endpoint
from . import packet_pb2
import src.config


@dataclass()
class Packet:
    from_: Endpoint
    to: Endpoint
    seq: int
    attempt: int
    acks: Set[Tuple[int, int]]
    payload: bytes
    is_syn: bool = False

    @staticmethod
    def from_message(msg: email.message.Message) -> Packet:
        if msg.get('X-Mailer') != src.config.config['tom']['X-Mailer']:
            raise Exception('invalid packet: invalid X-Mailer header')
        from_ = Endpoint(*reversed(parseaddr(msg.get('From'))))
        to = Endpoint(*reversed(parseaddr(msg.get('To'))))

        packet = packet_pb2.Packet()
        packet.ParseFromString(msg.get_payload(decode=True))
        seq = packet.id.seq
        attempt = packet.id.attempt
        acks = set((id.seq, id.attempt) for id in packet.acks)
        payload = packet.payload
        is_syn = packet.is_syn
        return Packet(from_, to, seq, attempt, acks, payload, is_syn)

    def to_message(self: Packet) -> email.message.Message:
        packet = packet_pb2.Packet()
        packet.id.seq = self.seq
        packet.id.attempt = self.attempt
        acks = []
        for seq, attempt in self.acks:
            id = packet_pb2.PacketId()
            id.seq = seq
            id.attempt = attempt
            acks.append(id)
        packet.acks.extend(acks)
        packet.payload = self.payload
        packet.is_syn = self.is_syn
        body = MIMEApplication(packet.SerializeToString(), 'x-mailim-packet', email.encoders.encode_base64)
        body.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        body.add_header('From', formataddr((self.from_.port, self.from_.address)))
        body.add_header('To', formataddr((self.to.port, self.to.address)))
        return body
