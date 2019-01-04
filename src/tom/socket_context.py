from enum import Enum
import threading
from . import Endpoint


class SocketStatus(Enum):
    CREATED = 0
    LISTENING = 1
    CONNECTED = 2


class SocketContext:
    status: SocketStatus = SocketStatus.CREATED


class SocketContextListening(SocketContext):
    status: SocketStatus = SocketStatus.LISTENING


class SocketContextConnected(SocketContext):
    status: SocketStatus = SocketStatus.CONNECTED
    local_endpoint: Endpoint
    remote_endpoint: Endpoint
    next_seq: int = 0
    incoming_data: bytes = b''
    cv: threading.Condition

    def __init__(self, local_endpoint: Endpoint, remote_endpoint: Endpoint):
        self.local_endpoint = local_endpoint
        self.remote_endpoint = remote_endpoint
        self.cv = threading.Condition()
