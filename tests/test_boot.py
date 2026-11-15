#!/usr/bin/env python3
"""Spec v0.3: the boot ROM clears memory, and VID_STAT is write-1-to-clear.

A 68000 program (tests/test_boot.s, built by fetch_build.sh into
work/test-boot.a16), loaded through the boot ROM's serial loader, checks and
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
from z80 import Asm as Z80  # noqa: E402
from test_ping import cartridge  # noqa: E402

DEFAULT_EMU = os.path.join(HERE, "..", "work", "cpcec")

PROGRAM = os.path.join(HERE, "..", "work", "test-boot.a16")


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
    if not os.path.exists(PROGRAM):
        print(f"no {PROGRAM}: run ./fetch_build.sh first")
        return 2
    tmp = tempfile.mkdtemp()
    cpr, serial = (os.path.join(tmp, n) for n in ("t.cpr", "ser.txt"))
    with open(cpr, "wb") as f:
        f.write(cartridge(z80_program()))
    with open(PROGRAM, "rb") as f:   # wrapped: 12 bytes of loader header, then the code
        assert len(f.read()) - 12 <= 0x1000, "test_boot.s outgrew 0x1000-0x1FFF, a checked range follows"
    subprocess.run([emu, "--headless", "--arnold16", "--a16-serial-in", os.path.abspath(PROGRAM),
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
