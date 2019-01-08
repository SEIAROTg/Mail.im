from enum import Enum
from typing import Dict, Tuple, Set, DefaultDict
from collections import defaultdict
import threading
from . import Endpoint
from .packet import Packet


class SocketStatus(Enum):
    CREATED = 0
    LISTENING = 1
    CONNECTED = 2


class SocketContext:
    status: SocketStatus = SocketStatus.CREATED
    closed: bool = False


class SocketContextListening(SocketContext):
    status: SocketStatus = SocketStatus.LISTENING


class SocketContextConnected(SocketContext):
    status: SocketStatus = SocketStatus.CONNECTED
    local_endpoint: Endpoint
    remote_endpoint: Endpoint
    next_seq: int = 0
    recv_cursor: Tuple[int, int] = (0, 0)                       # (seq, offset)
    pending_local: Dict[int, bytes]                             # seq -> payload
    pending_remote: Dict[int, bytes]                            # seq -> payload
    sent_acks: Dict[Tuple[int, int], Set[Tuple[int, int]]]      # (seq, attempt) -> {(seq, attempt)}
    attempts: DefaultDict[int, int]                             # seq -> next attempt
    to_ack: Set[Tuple[int, int]]                                # {(seq, attempt)}
    cv: threading.Condition

    def __init__(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        self.local_endpoint = local_endpoint
        self.remote_endpoint = remote_endpoint
        self.pending_local = {}
        self.pending_remote = {}
        self.sent_acks = {}
        self.attempts = defaultdict(int)
        self.to_ack = set()
        self.cv = threading.Condition()
