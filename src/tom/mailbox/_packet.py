from __future__ import annotations
from typing import Set, Tuple
import email.message
import email.encoders
from email.utils import parseaddr, formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dataclasses import dataclass
from .. import Endpoint
import src.config


@dataclass()
class Packet:
    from_: Endpoint
    to: Endpoint
    seq: int
    attempt: int
    acks: Set[Tuple[int, int]]
    payload: bytes

    @staticmethod
    def from_message(msg: email.message.Message) -> Packet:
        if msg.get('X-Mailer') != src.config.config['tom']['X-Mailer']:
            raise Exception('invalid packet: invalid X-Mailer header')
        from_ = Endpoint(*reversed(parseaddr(msg.get('From'))))
        to = Endpoint(*reversed(parseaddr(msg.get('To'))))
        try:
            seq, attempt = msg.get('Subject').rsplit('-', 1)
            seq = int(seq)
            attempt = int(attempt)
        except ValueError or AttributeError:
            raise Exception('invalid packet: invalid tid')
        try:
            acks, payload = msg.get_payload()
            acks = acks.get_payload()
            if acks != '':
                acks = acks.split('|')
                for i in range(len(acks)):
                    ack_seq, ack_attempt = acks[i].split('-')
                    acks[i] = (int(ack_seq), int(ack_attempt))
                acks = set(acks)
            else:
                acks = set()
        except ValueError:
            raise Exception('invalid packet: invalid acks')
        payload = payload.get_payload(decode=True)
        return Packet(from_, to, seq, attempt, acks, payload)

    def to_message(self: Packet) -> email.message.Message:
        body = MIMEMultipart()
        serialized_acks = '|'.join('-'.join(map(str, ack)) for ack in self.acks)
        acks = MIMEApplication(serialized_acks, 'mailim-acks', email.encoders.encode_noop)
        payload = MIMEApplication(self.payload, 'mailim-payload', email.encoders.encode_7or8bit)
        body.attach(acks)
        body.attach(payload)
        body.add_header('X-Mailer', src.config.config['tom']['X-Mailer'])
        body.add_header('Subject', '-'.join(map(str, (self.seq, self.attempt))))
        body.add_header('From', formataddr((self.from_.port, self.from_.address)))
        body.add_header('To', formataddr((self.to.port, self.to.address)))
        return body
