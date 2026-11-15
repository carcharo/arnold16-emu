#!/usr/bin/env python3
"""Builds the Arnold 16 boot ROM, version 0.3.

    python3 rom/mkboot.py work/arnold16.rom

What the ROM does:
  1. clears the exception vectors ($000008 to $0003FF), points the mailbox
     interrupt (level 2 autovector) at its handler and allows interrupts,
  2. prints a banner on the debug serial port,
  3. clears the rest of RAM and all of video RAM, so a program can rely on
     them starting at zero (RAM holds junk at power-on). This takes about
     0.55 s; PING is answered meanwhile,
  4. waits for a program on the serial port, copies it into RAM and jumps to
     it (the format is in tools/mkload.py).
While it waits, the mailbox handler takes every message from the Z80. It
answers PING (&7F) with the same four data bytes and drops everything else.
A loaded program starts in supervisor mode with interrupts allowed and takes
over the mailbox by pointing the level 2 vector at its own handler.

The ROM sits at $F00000. Its first eight bytes are the 68000 reset vectors,
which the hardware also shows at $000000: initial stack pointer, then start
address.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "asm"))
from m68k import *  # noqa: E402,F403

ROM_BASE = 0xF00000
ROM_SIZE = 0x10000
STACK_TOP = 0x100000          # top of the 1 MB of RAM
VECTOR_LEVEL2 = 0x68          # autovector for interrupt level 2
VECTORS_END = 0x400           # end of the 68000 exception vector table
VRAM = 0xE00000
VRAM_SIZE = 0x40000           # 256 KB

MBOX_CMD = 0xFF1001
MBOX_STAT = 0xFF1003
MBOX_DATA = 0xFF1004
SER_DATA = 0xFF2001
SER_STAT = 0xFF2003

PING = 0x7F
LOAD_MAGIC = 0x4131364C       # "A16L"
BANNER = "Arnold 16 boot ROM v0.3\n"


def build() -> bytes:
    a = Asm(org=ROM_BASE)
    a.l(STACK_TOP)                         # reset: initial stack pointer
    a.l("start")                           # reset: start address

    a.label("start")
    a.moveq(0, D4)                         # D4 stays zero while clearing
    a.lea(absl(8), A3)                     # the vectors first ($000000-7 is the ROM)
    a.move("w", imm((VECTORS_END - 8) // 4 - 1), D5)
    a.label("clear_vectors")
    a.move("l", D4, inc(A3))
    a.dbra(D5, "clear_vectors")
    a.move("l", imm("mailbox"), absl(VECTOR_LEVEL2))
    a.move_to_sr(0x2000)                   # supervisor mode, all interrupts allowed
    a.lea(pc("banner"), A0)
    a.bsr("puts")

    # --- clear RAM and video RAM, 32 bytes a time ---------------------------
    # Not in a subroutine: the stack at the top of RAM is cleared too, which is
    # safe only while nothing is on it. The mailbox handler saves and restores
    # what it uses, so it may run in between.
    for name, start, end in (("ram", VECTORS_END, STACK_TOP), ("vram", VRAM, VRAM + VRAM_SIZE)):
        a.lea(absl(start), A3)
        a.move("w", imm((end - start) // 32 - 1), D5)
        a.label("clear_" + name)
        for _ in range(8):
            a.move("l", D4, inc(A3))
        a.dbra(D5, "clear_" + name)

    # --- serial loader ----------------------------------------------------
    a.moveq(0, D1)
    a.label("find_magic")                  # shift bytes in until the last four are "A16L"
    a.bsr("getbyte")
    a.lsl("l", 8, D1)
    a.move("b", D0, D1)
    a.cmp("l", imm(LOAD_MAGIC), D1)
    a.bne("find_magic")
    a.bsr("getlong")                       # load address
    a.move("l", D1, A1)
    a.move("l", D1, A2)
    a.bsr("getlong")                       # length
    a.move("l", D1, D3)
    a.beq("run")
    a.label("copy")
    a.bsr("getbyte")
    a.move("b", D0, inc(A1))
    a.subq("l", 1, D3)
    a.bne("copy")
    a.label("run")
    a.lea(pc("loaded"), A0)
    a.bsr("puts")
    a.jmp(ind(A2))

    a.label("getbyte")                     # wait for a byte from the serial port, into D0
    a.btst(0, absl(SER_STAT))
    a.beq("getbyte")
    a.move("b", absl(SER_DATA), D0)
    a.rts()

    a.label("getlong")                     # four bytes, high byte first, into D1
    a.moveq(3, D2)
    a.label("getlong_next")
    a.bsr("getbyte")
    a.lsl("l", 8, D1)
    a.move("b", D0, D1)
    a.dbra(D2, "getlong_next")
    a.rts()

    a.label("puts")                        # print the zero-terminated string at A0
    a.move("b", inc(A0), D0)
    a.beq("puts_done")
    a.move("b", D0, absl(SER_DATA))
    a.bra("puts")
    a.label("puts_done")
    a.rts()

    # --- mailbox ------------------------------------------------------------
    a.label("mailbox")                     # level 2 interrupt: a message from the Z80
    a.move("l", D0, dec(SP))
    a.move("l", D1, dec(SP))
    a.move("l", absl(MBOX_DATA), D1)       # the data first: reading the command frees the mailbox
    a.move("b", absl(MBOX_CMD), D0)        # take the command; this also drops the interrupt
    a.cmp("b", imm(PING), D0)
    a.bne("mailbox_done")
    a.label("mailbox_wait")                # wait until the Z80 has taken our last message
    a.btst(1, absl(MBOX_STAT))
    a.bne("mailbox_wait")
    a.move("l", D1, absl(MBOX_DATA))
    a.move("b", imm(PING), absl(MBOX_CMD))
    a.label("mailbox_done")
    a.move("l", inc(SP), D1)
    a.move("l", inc(SP), D0)
    a.rte()

    a.label("banner")
    a.text(BANNER)
    a.label("loaded")
    a.text("Program loaded\n")

    code = a.assemble()
    if len(code) > ROM_SIZE:
        raise SystemExit("boot ROM is larger than 64 KB")
    return code.ljust(ROM_SIZE, b"\xFF")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "wb") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
