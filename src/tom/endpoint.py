from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Endpoint:
    address: str
    port: str

    def __hash__(self: Endpoint):
        return hash((self.address, self.port))

    def complete(self: Endpoint) -> bool:
        return (self.address != ''
                and self.port != ''
                and not self.address.startswith('@'))

    def matches(self: Endpoint, other: Endpoint) -> bool:
        address_match: bool = (
                self.address == ''
                or self.address == other.address
                or self.address.startswith('@') and other.address.endswith(self.address))
        port_match: bool = (self.port == ''
                            or self.port == other.port)
        return address_match and port_match

    def intersects_with(self: Endpoint, other: Endpoint) -> bool:
        address_intersect: bool = (
                self.address == ''
                or other.address == ''
                or self.address == other.address
                or self.address.startswith('@') and other.address.endswith(self.address)
                or other.address.startswith('@') and self.address.endswith(other.address))
        port_intersect: bool = (
                self.port == ''
                or other.port == ''
                or self.port == other.port)
        return address_intersect and port_intersect
