#!/usr/bin/env python3
"""The Arnold 16 ports, mailbox and 68000 boot ROM, driven from real Z80 code.

Builds a tiny cartridge whose Z80 program
  1. reads the ID port,
  2. sets RUN and reads STATUS,
  3. sends PING with four data bytes,
  4. waits for the reply and prints it,
then runs it in the patched CPCEC twice: with --arnold16 (the 68000 boot ROM
must print its banner on the serial port and answer the PING) and without (the
ports must look unused, as on a plain CPC).

The program prints through the CPC printer port, which CPCEC records to a file
(--printer), and ends the run with the marker CPCBuild's patch understands.

    python3 tests/test_ping.py [path/to/cpcec]
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
from z80 import Asm  # noqa: E402

DEFAULT_EMU = os.path.join(HERE, "..", "work", "cpcec")

ID, CTRL, STATUS, MBOX_CMD, MBOX_DATA = 0xF9E0, 0xF9E1, 0xF9E2, 0xF9E3, 0xF9E4
PRINTER = 0xEF00
PING = 0x7F
PAYLOAD = (0xDE, 0xAD, 0xBE, 0xEF)


def program() -> bytes:
    """The Z80 test program. It runs from cartridge page 0 at &0000."""
    a = Asm(org=0)
    a.di()
    a.ld_sp(0xC000)

    # 1. ID
    a.ld_hl("s_id"); a.call("puts")
    a.ld_bc(ID); a.in_a_c(); a.call("puthex"); a.call("newline")

    # 2. RUN, then STATUS
    a.ld_bc(CTRL); a.ld_a(1); a.out_c_a()
    a.ld_hl("s_st"); a.call("puts")
    a.ld_bc(STATUS); a.in_a_c(); a.call("puthex"); a.call("newline")

    # 3. PING: data bytes first, then the command
    for i, value in enumerate(PAYLOAD):
        a.ld_bc(MBOX_DATA + i); a.ld_a(value); a.out_c_a()
    a.ld_bc(MBOX_CMD); a.ld_a(PING); a.out_c_a()

    # 4. wait for STATUS bit 1 (a message from the 68000 is waiting)
    a.ld_de(0x4000)
    a.label("wait")
    a.ld_bc(STATUS); a.in_a_c(); a.and_n(2); a.jr_nz("got")
    a.dec_de(); a.ld_a_d(); a.or_e(); a.jr_nz("wait")
    a.ld_hl("s_timeout"); a.call("puts"); a.call("newline")
    a.jp("end")

    a.label("got")
    a.ld_hl("s_cmd"); a.call("puts")
    a.ld_bc(MBOX_CMD); a.in_a_c(); a.call("puthex"); a.call("newline")
    a.ld_hl("s_data"); a.call("puts")
    for i in range(4):
        a.ld_bc(MBOX_DATA + i); a.in_a_c(); a.call("puthex")
    a.call("newline")
    # STATUS again: both mailbox flags must be clear now
    a.ld_hl("s_st"); a.call("puts")
    a.ld_bc(STATUS); a.in_a_c(); a.call("puthex"); a.call("newline")

    a.label("end")
    a.ld_hl("s_end"); a.call("puts")
    a.label("stop"); a.jr("stop")

    # --- subroutines ------------------------------------------------------
    a.label("putc")          # print A: write it with bit 7 clear, then set
    a.ld_bc(PRINTER); a.and_n(0x7F); a.out_c_a(); a.or_n(0x80); a.out_c_a()
    a.ret()

    a.label("newline")
    a.ld_a(10); a.jr("putc")

    a.label("puts")          # print the zero-terminated string at HL
    a.ld_a_hl(); a.or_a(); a.ret_z()
    a.call("putc"); a.inc_hl(); a.jr("puts")

    a.label("puthex")        # print A as two hex digits
    a.push_af()
    a.rrca(); a.rrca(); a.rrca(); a.rrca()
    a.call("nibble")
    a.pop_af()
    a.label("nibble")
    a.and_n(0x0F); a.add_a(0x90); a.daa(); a.adc_a(0x40); a.daa()
    a.jr("putc")

    # --- strings ----------------------------------------------------------
    a.label("s_id"); a.text("ID=")
    a.label("s_st"); a.text("ST=")
    a.label("s_cmd"); a.text("CMD=")
    a.label("s_data"); a.text("DATA=")
    a.label("s_timeout"); a.text("TIMEOUT")
    a.label("s_end"); a.text("\x04END\n")
    return a.assemble()


def cartridge(code: bytes) -> bytes:
    """Wrap the program as a one-page Plus cartridge (.cpr, a RIFF file)."""
    page = code.ljust(16384, b"\0")
    chunk = b"cb00" + struct.pack("<I", len(page)) + page
    body = b"AMS!" + chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body


def run(emu: str, cpr: str, arnold: bool) -> tuple[str, str]:
    """Run the cartridge; return what it printed and what the 68000 sent to serial."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as out:
        printer = out.name
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as out:
        serial = out.name
    try:
        cmd = [emu, "--headless", "--printer", printer, "--end-on-marker",
               "--max-frames", "500"]
        if arnold:
            cmd += ["--arnold16", "--a16-serial", serial]
        cmd += ["-m3", cpr]
        subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(emu)),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=120, check=False)
        with open(printer, "rb") as f:
            printed = f.read().decode("ascii", "replace")
        with open(serial, "rb") as f:
            sent = f.read().decode("ascii", "replace")
        return printed, sent
    finally:
        os.unlink(printer)
        os.unlink(serial)


EXPECT_ARNOLD = "ID=16\nST=01\nCMD=7F\nDATA=DEADBEEF\nST=01\n\x04END\n"
EXPECT_SERIAL = "Arnold 16 boot ROM v0.2\n"
EXPECT_PLAIN = "ID=FF\nST=FF\nCMD=FF\nDATA=FFFFFFFF\nST=FF\n\x04END\n"


def main() -> int:
    emu = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMU)
    if not os.path.exists(emu):
        print(f"no emulator at {emu}: run ./fetch_build.sh first")
        return 2
    with tempfile.NamedTemporaryFile(suffix=".cpr", delete=False) as f:
        f.write(cartridge(program()))
        cpr = f.name
    failed = 0
    try:
        for name, arnold, expect, expect_serial in (
                ("PING answered by the 68000", True, EXPECT_ARNOLD, EXPECT_SERIAL),
                ("plain CPC is unchanged", False, EXPECT_PLAIN, "")):
            got, serial = run(emu, cpr, arnold)
            ok = got == expect and serial == expect_serial
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
            if not ok:
                failed += 1
                print(f"  printer: expected {expect!r}\n           got      {got!r}")
                print(f"  serial:  expected {expect_serial!r}\n           got      {serial!r}")
    finally:
        os.unlink(cpr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
