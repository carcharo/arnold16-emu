#!/usr/bin/env python3
"""Builds the Arnold 16 boot ROM, version 0.1.

    python3 rom/mkboot.py work/arnold16.rom

What the ROM does:
  1. prints a banner on the debug serial port,
  2. points the mailbox interrupt (level 2 autovector) at its handler,
  3. lowers the interrupt mask and sleeps (STOP) until an interrupt arrives.
The handler takes the message from the Z80. If it is PING (&7F) it sends the
same four data bytes back with the same command. Other commands are read and
dropped.

The ROM sits at $F00000. Its first eight bytes are the 68000 reset vectors,
which the hardware also shows at $000000: initial stack pointer, then start
address.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m68k import Asm  # noqa: E402

ROM_BASE = 0xF00000
ROM_SIZE = 0x10000
STACK_TOP = 0x100000          # top of the 1 MB of RAM
VECTOR_LEVEL2 = 0x68          # autovector for interrupt level 2

MBOX_CMD = 0xFF1001
MBOX_STAT = 0xFF1003
MBOX_DATA = 0xFF1004
SER_DATA = 0xFF2001

PING = 0x7F
BANNER = "Arnold 16 boot ROM v0.1\n"


def build() -> bytes:
    a = Asm(org=ROM_BASE)
    a.l(STACK_TOP)                     # reset: initial stack pointer
    a.l("start")                       # reset: start address

    a.label("start")
    a.lea_pc_a0("banner")
    a.bsr_s("puts")
    a.move_l_imm_absw("mailbox", VECTOR_LEVEL2)
    a.label("idle")
    a.stop(0x2000)                     # supervisor mode, all interrupts allowed; sleep
    a.bra_s("idle")

    a.label("puts")                    # print the zero-terminated string at A0
    a.move_b_a0inc_d0()
    a.beq_s("puts_done")
    a.move_b_d0_abs(SER_DATA)
    a.bra_s("puts")
    a.label("puts_done")
    a.rts()

    a.label("mailbox")                 # level 2 interrupt: a message from the Z80
    a.move_l_abs_d1(MBOX_DATA)         # the data first: reading the command frees the mailbox
    a.move_b_abs_d0(MBOX_CMD)          # take the command; this also drops the interrupt
    a.cmpi_b_d0(PING)
    a.bne_s("mailbox_done")
    a.label("mailbox_wait")            # wait until the Z80 has taken our last message
    a.btst_imm_abs(1, MBOX_STAT)
    a.bne_s("mailbox_wait")
    a.move_l_d1_abs(MBOX_DATA)
    a.move_b_imm_abs(PING, MBOX_CMD)
    a.label("mailbox_done")
    a.rte()

    a.label("banner")
    a.text(BANNER)

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
