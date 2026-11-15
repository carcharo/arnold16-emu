#!/usr/bin/env python3
"""Checks the Python 68000 assembler (asm/m68k.py) against Musashi's
disassembler: every instruction form the assembler can emit is assembled,
disassembled with work/dis68k, and compared with what was meant.

    python3 tests/test_asm.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
from m68k import *  # noqa: E402,F403

DIS = os.path.join(HERE, "..", "work", "dis68k")
ORG = 0x1000

# (how to emit it, what the disassembler must print)
CASES = [
    (lambda a: a.move("b", inc(A0), D0), "move.b  (A0)+, D0"),
    (lambda a: a.move("w", D0, absl(0xFF0004)), "move.w  D0, $ff0004.l"),
    (lambda a: a.move("l", imm(0x12345678), D1), "move.l  #$12345678, D1"),
    (lambda a: a.move("l", D1, A1), "movea.l D1, A1"),
    (lambda a: a.move("b", D0, inc(A1)), "move.b  D0, (A1)+"),
    (lambda a: a.move("l", D0, dec(SP)), "move.l  D0, -(A7)"),
    (lambda a: a.move("l", inc(SP), D0), "move.l  (A7)+, D0"),
    (lambda a: a.move("w", disp(4, A2), D3), "move.w  ($4,A2), D3"),
    (lambda a: a.move("b", imm(0x7F), absl(0xFF1001)), "move.b  #$7f, $ff1001.l"),
    (lambda a: a.move("l", imm("top"), absl(0x68)), "move.l  #$1000, $68.l"),
    (lambda a: a.move("w", A0, D0), "move.w  A0, D0"),
    (lambda a: a.move("w", inc(A0), inc(A1)), "move.w  (A0)+, (A1)+"),
    (lambda a: a.move("w", absl(0x80A), absl(0xFF0100)), "move.w  $80a.l, $ff0100.l"),
    (lambda a: a.moveq(-1, D7), "moveq   #-$1, D7"),
    (lambda a: a.moveq(3, D2), "moveq   #$3, D2"),
    (lambda a: a.lea(absl(0xE00000), A3), "lea     $e00000.l, A3"),
    (lambda a: a.lea(disp(-8, A6), A5), "lea     (-$8,A6), A5"),
    (lambda a: a.move_to_sr(0x2000), "move    #$2000, SR"),
    (lambda a: a.clr("w", D0), "clr.w   D0"),
    (lambda a: a.clr("b", absl(0x2000)), "clr.b   $2000.l"),
    (lambda a: a.clr("w", inc(A0)), "clr.w   (A0)+"),
    (lambda a: a.neg("l", D2), "neg.l   D2"),
    (lambda a: a.not_("b", D1), "not.b   D1"),
    (lambda a: a.tst("w", absl(0x2002)), "tst.w   $2002.l"),
    (lambda a: a.tst("b", D1), "tst.b   D1"),
    (lambda a: a.swap(D3), "swap    D3"),
    (lambda a: a.ext("w", D0), "ext.w   D0"),
    (lambda a: a.ext("l", D1), "ext.l   D1"),
    (lambda a: a.addq("w", 1, D0), "addq.w  #1, D0"),
    (lambda a: a.subq("l", 8, D3), "subq.l  #8, D3"),
    (lambda a: a.addq("l", 4, A0), "addq.l  #4, A0"),
    (lambda a: a.subq("b", 1, absl(0x3000)), "subq.b  #1, $3000.l"),
    (lambda a: a.add("w", D1, D0), "add.w   D1, D0"),
    (lambda a: a.add("w", imm(100), D0), "addi.w  #$64, D0"),
    (lambda a: a.add("w", imm(2), absl(0x3000)), "addi.w  #$2, $3000.l"),
    (lambda a: a.add("w", D0, absl(0x3000)), "add.w   D0, $3000.l"),
    (lambda a: a.add("l", absl(0x3000), D2), "add.l   $3000.l, D2"),
    (lambda a: a.sub("w", imm(96), D1), "subi.w  #$60, D1"),
    (lambda a: a.sub("b", D2, D3), "sub.b   D2, D3"),
    (lambda a: a.and_("w", imm(0x1FF), D0), "andi.w  #$1ff, D0"),
    (lambda a: a.and_("b", D1, D0), "and.b   D1, D0"),
    (lambda a: a.or_("b", imm(1), absl(0x3000)), "ori.b   #$1, $3000.l"),
    (lambda a: a.or_("w", D3, D4), "or.w    D3, D4"),
    (lambda a: a.eor("b", D3, D0), "eor.b   D3, D0"),
    (lambda a: a.eor("w", imm(0xFF), D1), "eori.w  #$ff, D1"),
    (lambda a: a.cmp("b", imm(0x7F), D0), "cmpi.b  #$7f, D0"),
    (lambda a: a.cmp("w", imm(200), absl(0x3000)), "cmpi.w  #$c8, $3000.l"),
    (lambda a: a.cmp("l", imm(0x4131364C), D1), "cmpi.l  #$4131364c, D1"),
    (lambda a: a.cmp("l", D1, D2), "cmp.l   D1, D2"),
    (lambda a: a.cmp("w", absl(0x3000), D0), "cmp.w   $3000.l, D0"),
    (lambda a: a.mulu(imm(512), D0), "mulu.w  #$200, D0"),
    (lambda a: a.lsl("l", 8, D1), "lsl.l   #8, D1"),
    (lambda a: a.lsr("w", 4, D0), "lsr.w   #4, D0"),
    (lambda a: a.asr("w", 1, D2), "asr.w   #1, D2"),
    (lambda a: a.btst(1, absl(0xFF1003)), "btst    #$1, $ff1003.l"),
    (lambda a: a.bclr(0, D0), "bclr    #$0, D0"),
    (lambda a: a.bset(7, ind(A0)), "bset    #$7, (A0)"),
    (lambda a: a.bra("top"), "bra     $1000"),
    (lambda a: a.bsr("top"), "bsr     $1000"),
    (lambda a: a.beq("top"), "beq     $1000"),
    (lambda a: a.bne("top"), "bne     $1000"),
    (lambda a: a.bpl("top"), "bpl     $1000"),
    (lambda a: a.bmi("top"), "bmi     $1000"),
    (lambda a: a.bcc("top"), "bcc     $1000"),
    (lambda a: a.bcs("top"), "bcs     $1000"),
    (lambda a: a.bhi("top"), "bhi     $1000"),
    (lambda a: a.bls("top"), "bls     $1000"),
    (lambda a: a.bge("top"), "bge     $1000"),
    (lambda a: a.blt("top"), "blt     $1000"),
    (lambda a: a.bgt("top"), "bgt     $1000"),
    (lambda a: a.ble("top"), "ble     $1000"),
    (lambda a: a.dbra(D2, "top"), "dbra    D2, $1000"),
    (lambda a: a.jmp(ind(A2)), "jmp     (A2)"),
    (lambda a: a.jsr(absl("top")), "jsr     $1000.l"),
    (lambda a: a.rts(), "rts"),
    (lambda a: a.rte(), "rte"),
    (lambda a: a.nop(), "nop"),
    (lambda a: a.stop(0x2000), "stop    #$2000"),
    # PC-relative forms: the disassembler adds the target address as a comment
    (lambda a: a.lea(pc("top"), A0), "; ($1000)"),
    (lambda a: a.move("w", pc("top"), D0), "; ($1000)"),
    (lambda a: a.jsr(pc("top")), "; ($1000)"),
    # a branch forward
    (lambda a: a.bra("end"), "bra     $END"),
]


def main() -> int:
    if not os.path.exists(DIS):
        print(f"no disassembler at {DIS}: run ./fetch_build.sh first")
        return 2
    a = Asm(org=ORG)
    a.label("top")
    for emit, _ in CASES:
        emit(a)
    a.label("end")
    end = a.labels["end"]
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(a.assemble())
        path = f.name
    try:
        out = subprocess.run([DIS, path, f"{ORG:x}"], capture_output=True,
                             text=True, check=True).stdout.splitlines()
    finally:
        os.unlink(path)
    failed = 0
    if len(out) != len(CASES):
        print(f"FAIL  {len(CASES)} instructions assembled, {len(out)} disassembled")
        failed += 1
    for line, (_, want) in zip(out, CASES):
        got = line[7:]
        want = want.replace("$END", f"${end:x}")
        ok = got.endswith(want) if want.startswith(";") else got == want
        if not ok:
            failed += 1
            print(f"FAIL  wanted {want!r}, got {got!r}")
    print(f"{'FAIL' if failed else 'PASS'}  68000 assembler: {len(CASES)} instruction forms")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
