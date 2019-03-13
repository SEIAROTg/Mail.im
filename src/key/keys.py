from __future__ import annotations
from typing import Dict, List, Tuple
from dataclasses import dataclass
from src.tom import Credential, Endpoint


Key = bytes


@dataclass
class Keys:
    email: Dict[str, Credential]
    local: List[Tuple[Tuple[Endpoint, Endpoint], Key]]
    remote: List[Tuple[Tuple[Endpoint, Endpoint], Key]]
    dumps: Dict[Tuple[Endpoint, Endpoint], bytes]

    def __init__(self):
        self.email = {}
        self.local = []
        self.remote = []
        self.dumps = {}

