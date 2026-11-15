"""A very small Z80 assembler for the tests and the demo's Z80 side: just the
instructions they use, with labels. Not a general tool.

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
    def jr_c(self, target: str): self._rel(0x38, target)
    def jr_nc(self, target: str): self._rel(0x30, target)
    def djnz(self, target: str): self._rel(0x10, target)

    # --- added for the demo's Z80 side ------------------------------------
    def ei(self): self.db(0xFB)
    def xor_a(self): self.db(0xAF)
    def xor_e(self): self.db(0xAB)
    def cpl(self): self.db(0x2F)
    def add_a_a(self): self.db(0x87)
    def inc_a(self): self.db(0x3C)
    def inc_c(self): self.db(0x0C)
    def cp_n(self, n: int): self.db(0xFE, n)
    def ld_b(self, n: int): self.db(0x06, n)
    def ld_h(self, n: int): self.db(0x26, n)
    def ld_a_e(self): self.db(0x7B)
    def ld_a_h(self): self.db(0x7C)
    def ld_a_l(self): self.db(0x7D)
    def ld_c_a(self): self.db(0x4F)
    def ld_d_a(self): self.db(0x57)
    def ld_e_a(self): self.db(0x5F)
    def ld_h_a(self): self.db(0x67)
    def ld_l_a(self): self.db(0x6F)
    def ld_l_c(self): self.db(0x69)
    def ld_hl_e(self): self.db(0x73)             # ld (hl),e
    def ld_a_mem(self, nn: int): self._abs(0x3A, nn)   # ld a,(nn)
    def ld_mem_a(self, nn: int): self._abs(0x32, nn)   # ld (nn),a
    def srl_d(self): self.db(0xCB, 0x3A)
    def srl_e(self): self.db(0xCB, 0x3B)
    def push_bc(self): self.db(0xC5)
    def push_de(self): self.db(0xD5)
    def pop_bc(self): self.db(0xC1)
    def pop_de(self): self.db(0xD1)
    def out_c_c(self): self.db(0xED, 0x49)       # out (c),c
    def out_c_d(self): self.db(0xED, 0x51)       # out (c),d
    def out_c_e(self): self.db(0xED, 0x59)       # out (c),e
    def out_c_h(self): self.db(0xED, 0x61)       # out (c),h
    def out_c_l(self): self.db(0xED, 0x69)       # out (c),l
