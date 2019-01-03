from __future__ import annotations
import email.message
import email.encoders
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dataclasses import dataclass
from ..config import config


@dataclass()
class Packet:
    seq: int
    payload: bytes

    @staticmethod
    def from_message(msg: email.message.Message) -> Packet:
        if msg.get('X-Mailer') != config['tom']['X-Mailer']:
            raise Exception('invalid packet: incorrect X-Mailer header')
        try:
            seq = int(msg.get('Subject'))
        except ValueError:
            raise Exception('invalid packet: invalid seq number')
        payload, = msg.get_payload()
        payload = payload.get_payload(decode=True)
        return Packet(seq, payload)

    def to_message(self: Packet) -> email.message.Message:
        body = MIMEMultipart()
        payload = MIMEApplication(self.payload, 'mailim-payload', email.encoders.encode_7or8bit)
        body.attach(payload)
        body.add_header('X-Mailer', config['tom']['X-Mailer'])
        body.add_header('Subject', str(self.seq))
        return body
