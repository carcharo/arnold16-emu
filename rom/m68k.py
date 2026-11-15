"""A very small 68000 assembler for the boot ROM: just the instructions the ROM
uses, with labels. Not a general tool. Replace it with a real assembler (vasm,
for example) once the ROM outgrows it.

Every method emits one instruction. Addresses are absolute; labels may be used
wherever a branch target or a PC-relative address is expected.
"""
from __future__ import annotations

import struct


class Asm:
    def __init__(self, org: int) -> None:
        self.org = org
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fix_rel8: list[tuple[int, str]] = []    # short branches
        self.fix_rel16: list[tuple[int, str]] = []   # (d16,PC)
        self.fix_abs32: list[tuple[int, str]] = []   # absolute long

    # --- plumbing ---------------------------------------------------------
    def here(self) -> int:
        return self.org + len(self.code)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"label {name} defined twice")
        if len(self.code) & 1:
            raise ValueError(f"label {name} at an odd address")
        self.labels[name] = self.here()

    def w(self, *words: int) -> None:
        for word in words:
            self.code += struct.pack(">H", word & 0xFFFF)

    def l(self, value: int | str) -> None:
        if isinstance(value, str):
            self.fix_abs32.append((len(self.code), value))
            value = 0
        self.code += struct.pack(">I", value & 0xFFFFFFFF)

    def text(self, s: str) -> None:
        """A zero-terminated string, padded to an even length."""
        data = s.encode("ascii") + b"\0"
        if len(data) & 1:
            data += b"\0"
        self.code += data

    def assemble(self) -> bytes:
        for at, name in self.fix_rel8:
            delta = self.labels[name] - (self.org + at + 1)  # from the word after the opcode
            if not -128 <= delta <= 127 or delta == 0:
                raise ValueError(f"short branch to {name} is out of range")
            self.code[at] = delta & 255
        for at, name in self.fix_rel16:
            delta = self.labels[name] - (self.org + at)       # from the extension word
            self.code[at:at + 2] = struct.pack(">h", delta)
        for at, name in self.fix_abs32:
            self.code[at:at + 4] = struct.pack(">I", self.labels[name])
        return bytes(self.code)

    def _bcc(self, opcode: int, target: str) -> None:
        self.code.append(opcode)
        self.fix_rel8.append((len(self.code), target))
        self.code.append(0)

    # --- instructions -----------------------------------------------------
    def bra_s(self, target: str): self._bcc(0x60, target)
    def bsr_s(self, target: str): self._bcc(0x61, target)
    def bne_s(self, target: str): self._bcc(0x66, target)
    def beq_s(self, target: str): self._bcc(0x67, target)
    def rts(self): self.w(0x4E75)
    def rte(self): self.w(0x4E73)

    def move_w_imm_sr(self, value: int):          # move.w #value,sr
        self.w(0x46FC, value)

    def stop(self, value: int):                   # stop #value
        self.w(0x4E72, value)

    def lea_pc_a0(self, target: str):             # lea target(pc),a0
        self.w(0x41FA)
        self.fix_rel16.append((len(self.code), target))
        self.w(0)

    def move_b_a0inc_d0(self):                    # move.b (a0)+,d0
        self.w(0x1018)

    def move_b_d0_abs(self, addr: int):           # move.b d0,addr
        self.w(0x13C0); self.l(addr)

    def move_b_abs_d0(self, addr: int):           # move.b addr,d0
        self.w(0x1039); self.l(addr)

    def move_b_imm_abs(self, value: int, addr: int):   # move.b #value,addr
        self.w(0x13FC, value & 255); self.l(addr)

    def move_l_abs_d1(self, addr: int):           # move.l addr,d1
        self.w(0x2239); self.l(addr)

    def move_l_d1_abs(self, addr: int):           # move.l d1,addr
        self.w(0x23C1); self.l(addr)

    def move_l_imm_absw(self, value: int | str, addr: int):  # move.l #value,addr.w
        self.w(0x21FC); self.l(value); self.w(addr)

    def cmpi_b_d0(self, value: int):              # cmpi.b #value,d0
        self.w(0x0C00, value & 255)

    def btst_imm_abs(self, bit: int, addr: int):  # btst #bit,addr
        self.w(0x0839, bit); self.l(addr)

    # --- added for the video tests ------------------------------------------
    def bpl_s(self, target: str): self._bcc(0x6A, target)

    def lea_abs_a0(self, addr: int):              # lea addr,a0
        self.w(0x41F9); self.l(addr)

    def move_w_a0_d0(self):                       # move.w a0,d0
        self.w(0x3008)

    def move_b_d0_a0inc(self):                    # move.b d0,(a0)+
        self.w(0x10C0)

    def move_b_imm_a0inc(self, value: int):       # move.b #value,(a0)+
        self.w(0x10FC, value & 255)

    def move_l_imm_d1(self, value: int):          # move.l #value,d1
        self.w(0x223C); self.l(value)

    def subq_l_1_d1(self):                        # subq.l #1,d1
        self.w(0x5381)

    def move_w_imm_abs(self, value: int, addr: int):   # move.w #value,addr
        self.w(0x33FC, value); self.l(addr)

    def move_w_abs_d0(self, addr: int):           # move.w addr,d0
        self.w(0x3039); self.l(addr)
