from typing import Dict, Tuple, Set, DefaultDict, Deque
from collections import defaultdict, deque
import threading
from .. import Endpoint


class SocketContext:
    closed: bool = False
    mutex: threading.RLock

    def __init__(self):
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
    next_seq: int = 0
    recv_cursor: Tuple[int, int] = (0, 0)                       # (seq, offset)
    pending_local: Dict[int, bytes]                             # seq -> payload
    pending_remote: Dict[int, bytes]                            # seq -> payload
    sent_acks: Dict[Tuple[int, int], Set[Tuple[int, int]]]      # (seq, attempt) -> {(seq, attempt)}
    attempts: DefaultDict[int, int]                             # seq -> next attempt
    to_ack: Set[Tuple[int, int]]                                # {(seq, attempt)}

    def __init__(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        super().__init__()
        self.local_endpoint = local_endpoint
        self.remote_endpoint = remote_endpoint
        self.pending_local = {}
        self.pending_remote = {}
        self.sent_acks = {}
        self.attempts = defaultdict(int)
        self.to_ack = set()


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
