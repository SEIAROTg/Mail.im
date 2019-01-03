from typing import NamedTuple


class Credential(NamedTuple):
    host: str
    port: int
    username: str
    password: str
