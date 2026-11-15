"""A very small Z80 assembler for the test programs: just the instructions the
tests use, with labels. Not a general tool.

    a = Asm(org=0)
    a.label("loop"); a.ld_a(1); a.jr("loop")
    code = a.assemble()
"""
from __future__ import annotations


class Asm:
    def __init__(self, org: int = 0) -> None:
        self.org = org
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fix16: list[tuple[int, str]] = []  # (offset of the 2-byte address, label)
        self.fix8: list[tuple[int, str]] = []   # (offset of the relative byte, label)

    # --- plumbing ---------------------------------------------------------
    def here(self) -> int:
        return self.org + len(self.code)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"label {name} defined twice")
        self.labels[name] = self.here()

    def db(self, *values: int) -> None:
        self.code += bytes(values)

    def text(self, s: str) -> None:
        self.code += s.encode("ascii") + b"\0"

    def _abs(self, opcode: int, target: int | str) -> None:
        self.db(opcode)
        if isinstance(target, str):
            self.fix16.append((len(self.code), target))
            target = 0
        self.db(target & 255, target >> 8)

    def _rel(self, opcode: int, target: str) -> None:
        self.db(opcode)
        self.fix8.append((len(self.code), target))
        self.db(0)

    def assemble(self) -> bytes:
        for at, name in self.fix16:
            addr = self.labels[name]
            self.code[at] = addr & 255
            self.code[at + 1] = addr >> 8
        for at, name in self.fix8:
            delta = self.labels[name] - (self.org + at + 1)
            if not -128 <= delta <= 127:
                raise ValueError(f"jr to {name} is out of range")
            self.code[at] = delta & 255
        return bytes(self.code)

    # --- instructions -----------------------------------------------------
    def di(self): self.db(0xF3)
    def halt(self): self.db(0x76)
    def ret(self): self.db(0xC9)
    def ret_z(self): self.db(0xC8)
    def daa(self): self.db(0x27)
    def rrca(self): self.db(0x0F)
    def or_a(self): self.db(0xB7)
    def or_e(self): self.db(0xB3)
    def push_af(self): self.db(0xF5)
    def pop_af(self): self.db(0xF1)
    def inc_hl(self): self.db(0x23)
    def dec_de(self): self.db(0x1B)
    def ld_a_hl(self): self.db(0x7E)   # ld a,(hl)
    def ld_a_d(self): self.db(0x7A)
    def in_a_c(self): self.db(0xED, 0x78)    # in a,(c)  -- port is BC
    def out_c_a(self): self.db(0xED, 0x79)   # out (c),a -- port is BC
    def ld_a(self, n: int): self.db(0x3E, n)
    def and_n(self, n: int): self.db(0xE6, n)
    def or_n(self, n: int): self.db(0xF6, n)
    def add_a(self, n: int): self.db(0xC6, n)
    def adc_a(self, n: int): self.db(0xCE, n)
    def ld_bc(self, nn: int): self._abs(0x01, nn)
    def ld_de(self, nn: int): self._abs(0x11, nn)
    def ld_hl(self, nn: int | str): self._abs(0x21, nn)
    def ld_sp(self, nn: int): self._abs(0x31, nn)
    def call(self, target: str): self._abs(0xCD, target)
    def jp(self, target: str): self._abs(0xC3, target)
    def jr(self, target: str): self._rel(0x18, target)
    def jr_nz(self, target: str): self._rel(0x20, target)
    def jr_z(self, target: str): self._rel(0x28, target)
