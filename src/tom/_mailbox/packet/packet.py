from dataclasses import dataclass
from ... import Endpoint


@dataclass()
class Packet:
    from_ : Endpoint
    to: Endpoint
