from typing import Set
import threading


class EpollContext:
    rset: Set[int]
    xset: Set[int]
    rrset: Set[int]
    rxset: Set[int]
    cv: threading.Condition
    closed: bool = False

    def __init__(self):
        self.rset = set()
        self.xset = set()
        self.rrset = set()
        self.rxset = set()
        self.cv = threading.Condition()
