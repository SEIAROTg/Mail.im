from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Endpoint:
    address: str
    port: str

    def __hash__(self: Endpoint):
        return hash((self.address, self.port))

    def complete(self: Endpoint) -> bool:
        """
        Test if the endpoint is complete.

        An endpoint is complete iff it has full address and non-empty port.

        :return: a bool indicating whether the endpoint is complete.
        """
        return (self.address != ''
                and self.port != ''
                and not self.address.startswith('@'))

    def matches(self: Endpoint, other: Endpoint) -> bool:
        """
        Test if the endpoint matches another endpoint.

        Endpoint A matches endpoint B iff both the address and the port of A matches those of B respectively.
        The address of A matches the address of B iff
            (1) they are the same; or
            (2) the address of A is empty; or
            (3) the address of A is a domain starting with "@" and the address of B ends with it
        The port of A matches the port of B iff
            (1) the they are the same; or
            (2) the port of A is empty

        :param other: the endpoint to match .
        :return: a bool indicating whether the endpoint matches the other endpoint.
        """
        address_match: bool = (
                self.address == ''
                or self.address == other.address
                or self.address.startswith('@') and other.address.endswith(self.address))
        port_match: bool = (self.port == ''
                            or self.port == other.port)
        return address_match and port_match

    def intersects_with(self: Endpoint, other: Endpoint) -> bool:
        """
        Test if the endpoint intersects with another endpoint.

        A endpoint intersects with another endpoint iff there exists a complete endpoint that can be matched by
        both of them.

        :param other: the endpoint to test intersection with.
        :return: a bool indicating whether the endpoint intersects with the other endpoint.
        """
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
