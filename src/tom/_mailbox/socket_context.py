from typing import Dict, Tuple, Set, DefaultDict, Deque, List, Optional
from collections import defaultdict, deque
import threading
from src.crypto.doubleratchet import DoubleRatchet
from .packet import Packet
from .. import Endpoint


class SocketContext:
    closed: bool
    mutex: threading.RLock

    def __init__(self):
        self.closed = False
        self.mutex = threading.RLock()


class Created(SocketContext):
    pass


class Waitable(SocketContext):
    cv: threading.Condition

    def __init__(self):
        super().__init__()
        self.cv = threading.Condition(self.mutex)


class Epollable(SocketContext):
    repolls: Set[int]
    xepolls: Set[int]

    def __init__(self):
        super().__init__()
        self.repolls = set()
        self.xepolls = set()


class Connected(Waitable, Epollable):
    local_endpoint: Endpoint
    remote_endpoint: Endpoint
    next_seq: int
    recv_cursor: Tuple[int, int]                                # (seq, offset)
    pending_local: Dict[int, Packet]                            # seq -> payload
    pending_remote: Dict[int, bytes]                            # seq -> payload
    sent_acks: Dict[Tuple[int, int], Set[Tuple[int, int]]]      # (seq, attempt) -> {(seq, attempt)}
    attempts: DefaultDict[int, int]                             # seq -> next attempt
    to_ack: Set[Tuple[int, int]]                                # {(seq, attempt)}
    syn_seq: int
    ack_scheduled: bool
    __STATE_KEYS: List[str] = [
        'local_endpoint',
        'remote_endpoint',
        'next_seq',
        'recv_cursor',
        'pending_local',
        'pending_remote',
        'sent_acks',
        'attempts',
        'to_ack',
        'syn_seq',
        'ack_scheduled',
    ]

    def __init__(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        super().__init__()
        self.local_endpoint = local_endpoint
        self.remote_endpoint = remote_endpoint
        self.next_seq = 0
        self.recv_cursor = (0, 0)
        self.pending_local = {}
        self.pending_remote = {}
        self.sent_acks = {}
        self.attempts = defaultdict(int)
        self.to_ack = set()
        self.syn_seq = None
        self.ack_scheduled = False

    def __getstate__(self):
        return {
            k: v
            for k, v in self.__dict__.items() if k in self.__class__.__STATE_KEYS
        }

    def __setstate__(self, state):
        super().__init__()
        self.__dict__.update({
            k: v
            for k, v in state.items() if k in self.__class__.__STATE_KEYS
        })
        if self.pending_local:
            self.syn_seq = min(self.pending_local.keys())
        else:
            self.syn_seq = self.next_seq
        self.ack_scheduled = False


class SecureConnected(Connected):
    handshaked: bool
    ratchet: DoubleRatchet

    def __init__(
            self,
            local_endpoint: Endpoint,
            remote_endpoint: Endpoint,
            own_key: Optional[bytes] = None,
            other_pub: Optional[bytes] = None):
        super().__init__(local_endpoint, remote_endpoint)
        self.handshaked = False
        self.ratchet = DoubleRatchet(own_key, other_pub)

    def __getstate__(self):
        state_self = (self.handshaked, self.ratchet.serialize())
        state_base = super().__getstate__()
        return state_base, state_self

    def __setstate__(self, state):
        state_base, state_self = state
        super().__setstate__(state_base)
        self.handshaked = state_self[0]
        self.ratchet = DoubleRatchet.fromSerialized(state_self[1])


class Listening(Waitable, Epollable):
    local_endpoint: Endpoint
    queue: Deque[int]                                           # [sid]
    connected_sockets: Dict[Tuple[Endpoint, Endpoint], int]     # (local_endpoint, remote_endpoint) -> sid
    sockets: Dict[int, Connected]                               # sid -> context

    def __init__(self, local_endpoint: Endpoint):
        super().__init__()
        self.local_endpoint = local_endpoint
        self.queue = deque()
        self.connected_sockets = {}
        self.sockets = {}
