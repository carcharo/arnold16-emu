#!/usr/bin/env python3
"""Spec v0.3: the boot ROM clears memory, and VID_STAT is write-1-to-clear.

A 68000 program, loaded through the boot ROM's serial loader, checks and
reports on the serial port:

  * RAM and video RAM are zero when it starts. The emulator fills both with
    junk at power-on, as real RAM would hold, so this passes only because the
    boot ROM cleared them.
  * Frame and raster events on the same line (RASTER_LINE = 200) both set
    their VID_STAT bit. Reading VID_STAT changes nothing; writing 1 to one bit
    clears that bit and leaves the other. Under spec v0.2 a read cleared both,
    so a frame handler silently dropped a raster interrupt due on line 200.

The interrupts stay disabled in VID_CTRL: the bits are set anyway (spec), so
the program polls them.

The Z80 side is a cartridge that only sets RUN. The run ends on a frame limit.

    python3 tests/test_boot.py [path/to/cpcec]
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from z80 import Asm as Z80  # noqa: E402
from m68k import *  # noqa: E402,F403
from test_ping import cartridge  # noqa: E402
from mkload import wrap  # noqa: E402

DEFAULT_EMU = os.path.join(HERE, "..", "work", "cpcec")

LOAD = 0x1000                 # where the test program is loaded
CHECKED = (                   # (start, end) ranges that must read as zero
    (0x000400, LOAD),         # RAM above the vectors, below the program
    (0x002000, 0x0FF000),     # RAM above the program, below the stack
    (0xE00000, 0xE40000),     # all of video RAM
)
VID_STAT, RASTER_LINE = 0xFF0002, 0xFF0008
SER_DATA = 0xFF2001


def program() -> bytes:
    a = Asm(org=LOAD)

    def report(char: str) -> None:
        a.move("b", imm(ord(char)), absl(SER_DATA))

    def report_vstat() -> None:      # VID_STAT's low byte, as one digit 0-7
        a.move("b", absl(VID_STAT + 1), D0)
        a.add("b", imm(ord("0")), D0)
        a.move("b", D0, absl(SER_DATA))

    # 1. memory: OR every long word of each range together; zero means clear
    report("M")
    for n, (start, end) in enumerate(CHECKED):
        a.lea(absl(start), A0)
        a.move("l", imm((end - start) // 4), D1)
        a.moveq(0, D2)
        a.label(f"or_{n}")
        a.or_("l", inc(A0), D2)
        a.subq("l", 1, D1)
        a.bne(f"or_{n}")
        a.tst("l", D2)
        a.beq(f"zero_{n}")
        report("!")                  # this range was not cleared
        a.bra(f"next_{n}")
        a.label(f"zero_{n}")
        report("0")
        a.label(f"next_{n}")
    report("\n")

    # 2. VID_STAT: frame and raster on the same line
    a.move("w", imm(200), absl(RASTER_LINE))
    a.move("w", imm(6), absl(VID_STAT))      # start from a clean state
    a.label("wait")                          # until the frame event has happened
    a.btst(1, absl(VID_STAT + 1))
    a.beq("wait")
    report("S")
    report_vstat()                           # 7: vblank, frame, raster
    report_vstat()                           # 7 again: the read cleared nothing
    a.move("w", imm(2), absl(VID_STAT))      # clear the frame bit only
    report_vstat()                           # 5: raster still pending
    a.move("w", imm(4), absl(VID_STAT))      # clear the raster bit
    report_vstat()                           # 1: only vblank left
    report("\n")

    a.label("idle")
    a.bra("idle")
    return a.assemble()


def z80_program() -> bytes:
    a = Z80(org=0)
    a.di()
    a.ld_bc(0xF9E1); a.ld_a(1); a.out_c_a()   # CTRL: RUN
    a.label("stop"); a.jr("stop")
    return a.assemble()


EXPECT_SERIAL = ("Arnold 16 boot ROM v0.3\nProgram loaded\n"
                 "M000\n"
                 "S7751\n")


def main() -> int:
    emu = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMU)
    if not os.path.exists(emu):
        print(f"no emulator at {emu}: run ./fetch_build.sh first")
        return 2
    tmp = tempfile.mkdtemp()
    cpr, load, serial = (os.path.join(tmp, n) for n in ("t.cpr", "t.a16", "ser.txt"))
    with open(cpr, "wb") as f:
        f.write(cartridge(z80_program()))
    code = program()
    assert LOAD + len(code) <= CHECKED[1][0], "test program overlaps a checked range"
    with open(load, "wb") as f:
        f.write(wrap(code, LOAD))
    subprocess.run([emu, "--headless", "--arnold16", "--a16-serial-in", load,
                    "--a16-serial", serial, "--max-frames", "200", "-m3", cpr],
                   cwd=os.path.dirname(emu), stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=180, check=False)
    with open(serial, "rb") as f:
        got = f.read().decode("ascii", "replace")

    failed = 0
    lines = got.split("\n")
    expect = EXPECT_SERIAL.split("\n")
    for name, i in (("boot ROM banner and loader", slice(0, 2)),
                    ("RAM and video RAM are clear after boot (3 ranges)", slice(2, 3)),
                    ("VID_STAT: read keeps bits, writing 1 clears only that bit", slice(3, 4))):
        ok = lines[i] == expect[i]
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failed += 1
            print(f"  expected {expect[i]!r}\n  got      {lines[i]!r}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
