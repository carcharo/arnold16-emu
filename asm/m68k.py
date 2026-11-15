"""A small 68000 assembler in Python, for the boot ROM, the demo and the tests.

It covers the common instructions and addressing modes, not the whole 68000.
tests/test_asm.py checks every form it can emit against Musashi's
disassembler. Replace it with a real assembler (vasm or GNU as) if the project
outgrows it.

    from m68k import *
    a = Asm(org=0x1000)
    a.label("loop")
    a.move("b", inc(A0), D0)        # move.b (a0)+,d0
    a.bne("loop")
    code = a.assemble()

Operands
    D0..D7, A0..A7, SP      registers
    ind(A0)                 (a0)
    inc(A0)                 (a0)+
    dec(A0)                 -(a0)
    disp(8, A0)             8(a0)
    absl(0xFF0000)          absolute address; absl("label") also works
    pc("label")             label(pc)
    imm(5)                  #5; imm("label") is the address of a label (long only)

Sizes are "b", "w" or "l". Branches always use 16-bit displacements.
"""
from __future__ import annotations

import struct

__all__ = ["Asm", "ind", "inc", "dec", "disp", "absl", "pc", "imm", "SP",
           "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
           "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7"]


class _Op:
    def __init__(self, kind: str, reg: int = 0, value: int | str = 0) -> None:
        self.kind, self.reg, self.value = kind, reg, value

    def __repr__(self) -> str:
        return f"<{self.kind} {self.reg} {self.value}>"


D0, D1, D2, D3, D4, D5, D6, D7 = (_Op("d", n) for n in range(8))
A0, A1, A2, A3, A4, A5, A6, A7 = (_Op("a", n) for n in range(8))
SP = A7


def _areg(r: _Op) -> int:
    if r.kind != "a":
        raise ValueError("an address register is needed here")
    return r.reg


def ind(r: _Op) -> _Op: return _Op("ind", _areg(r))
def inc(r: _Op) -> _Op: return _Op("inc", _areg(r))
def dec(r: _Op) -> _Op: return _Op("dec", _areg(r))
def disp(d: int, r: _Op) -> _Op: return _Op("disp", _areg(r), d)
def absl(addr: int | str) -> _Op: return _Op("abs", 0, addr)
def pc(label: str) -> _Op: return _Op("pc", 0, label)
def imm(value: int | str) -> _Op: return _Op("imm", 0, value)


_SIZE_MOVE = {"b": 1, "w": 3, "l": 2}     # size field of MOVE
_SIZE = {"b": 0, "w": 1, "l": 2}          # size field of most other instructions
_CONDITIONS = {"ra": 0, "sr": 1, "hi": 2, "ls": 3, "cc": 4, "cs": 5, "ne": 6,
               "eq": 7, "vc": 8, "vs": 9, "pl": 10, "mi": 11, "ge": 12,
               "lt": 13, "gt": 14, "le": 15}


class Asm:
    def __init__(self, org: int) -> None:
        self.org = org
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fix_rel16: list[tuple[int, str]] = []   # 16-bit, relative to the word itself
        self.fix_abs32: list[tuple[int, str]] = []

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
        """Raw 16-bit words."""
        for word in words:
            self.code += struct.pack(">H", word & 0xFFFF)

    def l(self, value: int | str) -> None:
        """A raw 32-bit value, or the address of a label."""
        if isinstance(value, str):
            self.fix_abs32.append((len(self.code), value))
            value = 0
        self.code += struct.pack(">I", value & 0xFFFFFFFF)

    def data(self, raw: bytes) -> None:
        """Raw bytes, padded to an even length."""
        self.code += raw
        if len(self.code) & 1:
            self.code.append(0)

    def text(self, s: str) -> None:
        """A zero-terminated string, padded to an even length."""
        self.data(s.encode("ascii") + b"\0")

    def assemble(self) -> bytes:
        for at, name in self.fix_rel16:
            delta = self.labels[name] - (self.org + at)
            if not -32768 <= delta <= 32767:
                raise ValueError(f"{name} is too far away")
            self.code[at:at + 2] = struct.pack(">h", delta)
        for at, name in self.fix_abs32:
            self.code[at:at + 4] = struct.pack(">I", self.labels[name])
        return bytes(self.code)

    def _rel16(self, label: str) -> None:
        self.fix_rel16.append((len(self.code), label))
        self.w(0)

    # --- effective addresses ----------------------------------------------
    def _ea(self, op: _Op, size: str, allow: str) -> tuple[int, list]:
        """Return (mode<<3 | reg, extension) for an operand. `allow` lists the
        operand kinds the instruction takes. The extension is a list of
        ("w", value), ("l", value) or ("pc", label) items, emitted by _ext()."""
        if op.kind not in allow.split():
            raise ValueError(f"operand {op!r} is not allowed here")
        k = op.kind
        if k == "d": return 0o00 | op.reg, []
        if k == "a": return 0o10 | op.reg, []
        if k == "ind": return 0o20 | op.reg, []
        if k == "inc": return 0o30 | op.reg, []
        if k == "dec": return 0o40 | op.reg, []
        if k == "disp": return 0o50 | op.reg, [("w", op.value)]
        if k == "abs": return 0o71, [("l", op.value)]
        if k == "pc": return 0o72, [("pc", op.value)]
        if k == "imm":
            if size == "l":
                return 0o74, [("l", op.value)]
            if isinstance(op.value, str):
                raise ValueError("the address of a label needs size l")
            return 0o74, [("w", op.value & (0xFF if size == "b" else 0xFFFF))]
        raise ValueError(f"unknown operand {op!r}")

    def _ext(self, ext: list) -> None:
        for kind, value in ext:
            if kind == "w":
                self.w(value)
            elif kind == "l":
                self.l(value)
            else:
                self._rel16(value)

    _SRC = "d a ind inc dec disp abs pc imm"       # anything readable
    _DATA = "d ind inc dec disp abs pc imm"        # readable, not An
    _ALT = "d ind inc dec disp abs"                # writable data
    _MEM = "ind inc dec disp abs"                  # writable memory
    _CTRL = "ind disp abs pc"                      # jump and lea targets

    # --- moves ------------------------------------------------------------
    def move(self, size: str, src: _Op, dst: _Op) -> None:
        """move / movea"""
        if dst.kind == "a" and size == "b":
            raise ValueError("movea has no byte size")
        s, sx = self._ea(src, size, self._SRC)
        d, dx = self._ea(dst, size, "a " + self._ALT)
        self.w((_SIZE_MOVE[size] << 12) | ((d & 7) << 9) | ((d >> 3) << 6) | s)
        self._ext(sx)
        self._ext(dx)

    def moveq(self, value: int, dst: _Op) -> None:
        if dst.kind != "d" or not -128 <= value <= 127:
            raise ValueError("moveq takes -128..127 and a data register")
        self.w(0x7000 | (dst.reg << 9) | (value & 0xFF))

    def lea(self, src: _Op, dst: _Op) -> None:
        s, sx = self._ea(src, "l", self._CTRL)
        self.w(0x41C0 | (_areg(dst) << 9) | s)
        self._ext(sx)

    def move_to_sr(self, value: int) -> None:      # move.w #value,sr
        self.w(0x46FC, value)

    # --- one operand ------------------------------------------------------
    def _one(self, base: int, size: str, dst: _Op) -> None:
        d, dx = self._ea(dst, size, self._ALT)
        self.w(base | (_SIZE[size] << 6) | d)
        self._ext(dx)

    def clr(self, size: str, dst: _Op): self._one(0x4200, size, dst)
    def neg(self, size: str, dst: _Op): self._one(0x4400, size, dst)
    def not_(self, size: str, dst: _Op): self._one(0x4600, size, dst)
    def tst(self, size: str, dst: _Op): self._one(0x4A00, size, dst)

    def swap(self, dst: _Op) -> None:
        if dst.kind != "d":
            raise ValueError("swap takes a data register")
        self.w(0x4840 | dst.reg)

    def ext(self, size: str, dst: _Op) -> None:    # ext.w (byte to word), ext.l (word to long)
        if dst.kind != "d" or size not in "wl":
            raise ValueError("ext takes w or l and a data register")
        self.w((0x4880 if size == "w" else 0x48C0) | dst.reg)

    # --- arithmetic and logic ---------------------------------------------
    def _quick(self, base: int, size: str, value: int, dst: _Op) -> None:
        if not 1 <= value <= 8:
            raise ValueError("addq and subq take 1..8")
        if dst.kind == "a" and size == "b":
            raise ValueError("no byte size on an address register")
        d, dx = self._ea(dst, size, "a " + self._ALT)
        self.w(base | ((value & 7) << 9) | (_SIZE[size] << 6) | d)
        self._ext(dx)

    def addq(self, size: str, value: int, dst: _Op): self._quick(0x5000, size, value, dst)
    def subq(self, size: str, value: int, dst: _Op): self._quick(0x5100, size, value, dst)

    def _arith(self, base: int, immediate: int, size: str, src: _Op, dst: _Op) -> None:
        """add, sub, and, or: #imm,ea / ea,Dn / Dn,memory."""
        if src.kind == "imm" and dst.kind != "a":
            d, dx = self._ea(dst, size, self._ALT)
            self.w(immediate | (_SIZE[size] << 6) | d)
            self._ext(self._ea(src, size, "imm")[1])
            self._ext(dx)
        elif dst.kind == "d":
            s, sx = self._ea(src, size, self._SRC if base in (0xD000, 0x9000) else self._DATA)
            self.w(base | (dst.reg << 9) | (_SIZE[size] << 6) | s)
            self._ext(sx)
        elif src.kind == "d":
            d, dx = self._ea(dst, size, self._MEM)
            self.w(base | (src.reg << 9) | 0x100 | (_SIZE[size] << 6) | d)
            self._ext(dx)
        else:
            raise ValueError("one operand must be a data register or #immediate")

    def add(self, size, src, dst): self._arith(0xD000, 0x0600, size, src, dst)
    def sub(self, size, src, dst): self._arith(0x9000, 0x0400, size, src, dst)
    def and_(self, size, src, dst): self._arith(0xC000, 0x0200, size, src, dst)
    def or_(self, size, src, dst): self._arith(0x8000, 0x0000, size, src, dst)

    def eor(self, size: str, src: _Op, dst: _Op) -> None:
        """eor #imm,ea / eor Dn,ea"""
        d, dx = self._ea(dst, size, self._ALT)
        if src.kind == "imm":
            self.w(0x0A00 | (_SIZE[size] << 6) | d)
            self._ext(self._ea(src, size, "imm")[1])
        elif src.kind == "d":
            self.w(0xB100 | (src.reg << 9) | (_SIZE[size] << 6) | d)
        else:
            raise ValueError("eor takes a data register or #immediate as source")
        self._ext(dx)

    def cmp(self, size: str, src: _Op, dst: _Op) -> None:
        """cmp #imm,ea / cmp ea,Dn"""
        if src.kind == "imm":
            d, dx = self._ea(dst, size, self._ALT)
            self.w(0x0C00 | (_SIZE[size] << 6) | d)
            self._ext(self._ea(src, size, "imm")[1])
            self._ext(dx)
        elif dst.kind == "d":
            s, sx = self._ea(src, size, self._SRC)
            self.w(0xB000 | (dst.reg << 9) | (_SIZE[size] << 6) | s)
            self._ext(sx)
        else:
            raise ValueError("cmp needs #immediate as source or a data register as destination")

    def mulu(self, src: _Op, dst: _Op) -> None:    # mulu.w ea,Dn
        s, sx = self._ea(src, "w", self._DATA)
        if dst.kind != "d":
            raise ValueError("mulu needs a data register as destination")
        self.w(0xC0C0 | (dst.reg << 9) | s)
        self._ext(sx)

    def _shift(self, base: int, size: str, count: int, dst: _Op) -> None:
        if dst.kind != "d" or not 1 <= count <= 8:
            raise ValueError("shifts take a count of 1..8 and a data register")
        self.w(base | ((count & 7) << 9) | (_SIZE[size] << 6) | dst.reg)

    def lsl(self, size, count, dst): self._shift(0xE108, size, count, dst)
    def lsr(self, size, count, dst): self._shift(0xE008, size, count, dst)
    def asr(self, size, count, dst): self._shift(0xE000, size, count, dst)

    # --- bits -------------------------------------------------------------
    def _bit(self, base: int, bit: int, dst: _Op) -> None:
        d, dx = self._ea(dst, "b", self._ALT)
        self.w(base | d, bit)
        self._ext(dx)

    def btst(self, bit: int, dst: _Op): self._bit(0x0800, bit, dst)
    def bclr(self, bit: int, dst: _Op): self._bit(0x0880, bit, dst)
    def bset(self, bit: int, dst: _Op): self._bit(0x08C0, bit, dst)

    # --- flow -------------------------------------------------------------
    def _branch(self, condition: str, label: str) -> None:
        self.w(0x6000 | (_CONDITIONS[condition] << 8))
        self._rel16(label)

    def bra(self, label): self._branch("ra", label)
    def bsr(self, label): self._branch("sr", label)
    def beq(self, label): self._branch("eq", label)
    def bne(self, label): self._branch("ne", label)
    def bpl(self, label): self._branch("pl", label)
    def bmi(self, label): self._branch("mi", label)
    def bcc(self, label): self._branch("cc", label)     # unsigned >=
    def bcs(self, label): self._branch("cs", label)     # unsigned <
    def bhi(self, label): self._branch("hi", label)     # unsigned >
    def bls(self, label): self._branch("ls", label)     # unsigned <=
    def bge(self, label): self._branch("ge", label)
    def blt(self, label): self._branch("lt", label)
    def bgt(self, label): self._branch("gt", label)
    def ble(self, label): self._branch("le", label)

    def dbra(self, counter: _Op, label: str) -> None:
        if counter.kind != "d":
            raise ValueError("dbra counts in a data register")
        self.w(0x51C8 | counter.reg)
        self._rel16(label)

    def jmp(self, dst: _Op) -> None:
        d, dx = self._ea(dst, "l", self._CTRL)
        self.w(0x4EC0 | d)
        self._ext(dx)

    def jsr(self, dst: _Op) -> None:
        d, dx = self._ea(dst, "l", self._CTRL)
        self.w(0x4E80 | d)
        self._ext(dx)

    def rts(self): self.w(0x4E75)
    def rte(self): self.w(0x4E73)
    def nop(self): self.w(0x4E71)

    def stop(self, value: int) -> None:            # stop #value
        self.w(0x4E72, value)
