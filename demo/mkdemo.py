#!/usr/bin/env python3
"""Builds the Arnold 16 proof-of-concept demo.

    python3 demo/mkdemo.py work

writes into the directory given:
  demo.dsk            a CPC disc holding the Z80 side as DISC.BIN
  demo.inc            constants the 68000 program (demo/demo.s) shares with
                      this file and the tests
  demo-palette.bin    the palette, and
  demo-patterns.bin   the sprite patterns, which demo/demo.s includes

fetch_build.sh then assembles demo/demo.s with GNU as into demo.a16, the
68000 program wrapped for the boot ROM's serial loader.

Run it with
    work/cpcec --arnold16 --a16-serial-in work/demo.a16 -m2 work/demo.dsk

CPCEC boots the 6128 to BASIC and types RUN"DISC itself. On a real machine,
type RUN"DISC.

The Z80 side loads at &4000 from BASIC. It takes over the machine (no
firmware from then on), programs the CRTC, starts the 68000 with the new
display on, and then serves it: it scans the keyboard and sends a KEY message
for every key that goes down or up, writes the AY sound chip when asked
(AY_WRITE), and on EXIT puts the 68000 back into reset and resets the CPC,
which comes back to the BASIC start-up screen. It also logs what it does to
the printer port, which the tests read.

The 68000 side, in demo/demo.s, fills the 512 x 256 bitmap with a pattern,
scrolls it one pixel per frame, moves three sprites across it, and lets the
cursor keys steer a fourth. SPACE plays a short beep. ESC ends the demo.
"""
from __future__ import annotations

import colorsys
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from z80 import Asm as Z80  # noqa: E402
from mkdsk import DiskImage  # noqa: E402

# --- hardware, from the spec ------------------------------------------------
PORT_CTRL, PORT_STATUS, PORT_CMD, PORT_DATA = 0xF9E1, 0xF9E2, 0xF9E3, 0xF9E4
CMD_KEY, CMD_AY_WRITE, CMD_EXIT = 1, 2, 3

# shared with demo/demo.s through demo.inc
PLAYER_START = (152, 92)
PLAYER_STEP = 2                 # pixels per frame while a cursor key is held
BEEP_FRAMES = 10

# palette indexes with fixed colours, used by the sprites
WHITE, YELLOW, RED, CYAN, NAVY = 255, 254, 253, 252, 251


# --- pictures, made here rather than on the 68000 ---------------------------
def palette() -> bytes:
    """256 entries of 0RGB: a rainbow for the bitmap, fixed colours on top."""
    words = []
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb(i / 256, 0.85, 0.35 + 0.5 * (i & 15) / 15)
        words.append((round(r * 15) << 8) | (round(g * 15) << 4) | round(b * 15))
    words[WHITE], words[YELLOW], words[RED], words[CYAN], words[NAVY] = 0xFFF, 0xFE0, 0xF22, 0x0EF, 0x013
    return struct.pack(">256H", *words)


def ball() -> bytes:
    """Sprite pattern 0: the player's ball, 16 x 16, colour 0 transparent."""
    rows = []
    for y in range(16):
        for x in range(16):
            d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
            rows.append(0 if d > 7.6 else NAVY if d > 6.4 else
                        WHITE if (x - 5) ** 2 + (y - 5) ** 2 < 6 else YELLOW)
    return bytes(rows)


def diamond() -> bytes:
    """Sprite pattern 1: a diamond."""
    rows = []
    for y in range(16):
        for x in range(16):
            d = abs(x - 7.5) + abs(y - 7.5)
            rows.append(0 if d > 8 else NAVY if d > 6.5 else RED if d > 3 else CYAN)
    return bytes(rows)


def include() -> str:
    """demo.inc: the constants demo/demo.s shares with this file and the tests."""
    values = {"PLAYER_X0": PLAYER_START[0], "PLAYER_Y0": PLAYER_START[1],
              "PLAYER_STEP": PLAYER_STEP, "BEEP_FRAMES": BEEP_FRAMES, "NAVY": NAVY}
    lines = ["| made by demo/mkdemo.py: do not edit"]
    lines += [f"        .equ    {name}, {value}" for name, value in values.items()]
    return "\n".join(lines) + "\n"


# --- the Z80 side -----------------------------------------------------------
# the CRTC values the CPC firmware sets for a 50 Hz screen, registers 0 to 13
CRTC = (63, 40, 46, 142, 38, 0, 25, 30, 0, 7, 0, 0, 48, 0)
PRINTER = 0xEF00
Z80_LOAD = 0x4000               # where DISC.BIN loads and starts
Z_LINE = 0x8100                 # variable: keyboard line being scanned
Z_PREVIOUS = 0x8000             # ten bytes: the keyboard lines as last seen


def z80_program() -> bytes:
    a = Z80(org=Z80_LOAD)
    a.di()                                  # the firmware is not used from here on
    a.ld_sp(0xC000)
    a.ld_bc(0xFA7E); a.xor_a(); a.out_c_a()         # disc motor off: AMSDOS would, but its ticker is stopped
    for register, value in enumerate(CRTC):
        a.ld_bc(0xBC00); a.ld_a(register); a.out_c_a()
        a.ld_bc(0xBD00); a.ld_a(value); a.out_c_a()
    for line in range(10):                  # no key is down yet (a 0 bit means down)
        a.ld_a(0xFF); a.ld_mem_a(Z_PREVIOUS + line)
    a.ld_bc(PORT_CTRL); a.ld_a(3); a.out_c_a()      # RUN + DISPLAY

    # --- serve the 68000 for ever ----------------------------------------
    a.label("serve")
    a.ld_bc(PORT_STATUS); a.in_a_c(); a.and_n(2)    # a message from the 68000?
    a.jr_z("keys")
    a.ld_bc(PORT_DATA); a.in_a_c(); a.ld_d_a()      # data byte 0
    a.ld_bc(PORT_DATA + 1); a.in_a_c(); a.ld_e_a()  # data byte 1
    a.ld_bc(PORT_CMD); a.in_a_c()                   # the command; this frees the mailbox
    a.cp_n(CMD_AY_WRITE); a.jr_nz("not_ay")
    a.call("ay_write")
    a.ld_a(ord("A")); a.call("putc")                # log: A, register, value
    a.ld_a_d(); a.call("puthex"); a.ld_a_e(); a.call("puthex"); a.call("newline")
    a.jr("keys")
    a.label("not_ay")
    a.cp_n(CMD_EXIT); a.jr_nz("keys")
    a.ld_bc(PORT_CTRL); a.xor_a(); a.out_c_a()      # 68000 into reset, CPC screen back
    a.ld_hl("s_exit"); a.call("puts")
    a.ld_bc(0x7F89); a.out_c_c()                    # lower ROM on, upper off, mode 1, as at power-on ...
    a.jp(0)                                         # ... and the firmware's reset: back to BASIC

    a.label("keys")
    a.call("scan")
    a.jp("serve")

    # --- scan the keyboard; send KEY for every key that changed ----------
    a.label("scan")
    a.xor_a(); a.ld_mem_a(Z_LINE)
    a.label("scan_line")
    a.ld_a_mem(Z_LINE); a.call("read_line"); a.ld_e_a()        # E = the line now
    a.ld_a_mem(Z_LINE); a.ld_l_a(); a.ld_h(Z_PREVIOUS >> 8)    # HL = where it was kept
    a.ld_a_hl(); a.xor_e(); a.jr_z("scan_next")                # A = the bits that changed
    a.ld_hl_e(); a.ld_d_a()                                    # D = changed bits, E = state
    a.ld_a_mem(Z_LINE); a.add_a_a(); a.add_a_a(); a.add_a_a(); a.ld_c_a()   # C = key number of bit 0
    a.ld_b(8)
    a.label("scan_bit")
    a.srl_d(); a.jr_nc("scan_same")                 # did this key change?
    a.ld_a_e(); a.cpl(); a.and_n(1); a.ld_h_a()     # H = 1 if it is down now
    a.ld_l_c()                                      # L = key number
    a.push_bc(); a.push_de()
    a.call("send_key")
    a.pop_de(); a.pop_bc()
    a.label("scan_same")
    a.srl_e(); a.inc_c(); a.djnz("scan_bit")
    a.label("scan_next")
    a.ld_a_mem(Z_LINE); a.inc_a(); a.ld_mem_a(Z_LINE)
    a.cp_n(10); a.jr_c("scan_line")
    a.ret()

    a.label("send_key")            # KEY message: L = key number, H = 1 down, 0 up
    a.ld_bc(PORT_STATUS); a.in_a_c(); a.and_n(4)    # wait until the 68000 took the last one
    a.jr_nz("send_key")
    a.ld_bc(PORT_DATA); a.out_c_l()
    a.ld_bc(PORT_DATA + 1); a.out_c_h()
    a.ld_bc(PORT_CMD); a.ld_a(CMD_KEY); a.out_c_a()
    a.ld_a(ord("K")); a.call("putc")                # log: K, key number, state
    a.ld_a_l(); a.call("puthex"); a.ld_a_h(); a.call("puthex")
    a.jp("newline")

    a.label("read_line")           # read keyboard line A through the sound chip; 0 bits are keys down
    a.push_af()
    a.ld_bc(0xF40E); a.out_c_c()   # sound chip register 14 (the keyboard) ...
    a.ld_bc(0xF6C0); a.out_c_c()   # ... selected
    a.ld_bc(0xF600); a.out_c_c()
    a.ld_bc(0xF792); a.out_c_c()   # PPI port A becomes an input
    a.pop_af()
    a.or_n(0x40)                   # read mode, with the line number
    a.ld_b(0xF6); a.out_c_a()
    a.ld_b(0xF4); a.in_a_c()       # the line
    a.ld_bc(0xF782); a.out_c_c()   # PPI port A back to output
    a.ld_bc(0xF600); a.out_c_c()
    a.ret()

    a.label("ay_write")            # write value E to sound chip register D
    a.ld_b(0xF4); a.out_c_d()
    a.ld_bc(0xF6C0); a.out_c_c()   # select the register
    a.ld_bc(0xF600); a.out_c_c()
    a.ld_b(0xF4); a.out_c_e()
    a.ld_bc(0xF680); a.out_c_c()   # write the value
    a.ld_bc(0xF600); a.out_c_c()
    a.ret()

    # --- printing to the printer port, for the log --------------------------
    a.label("putc")
    a.ld_bc(PRINTER); a.and_n(0x7F); a.out_c_a(); a.or_n(0x80); a.out_c_a()
    a.ret()
    a.label("newline")
    a.ld_a(10); a.jr("putc")
    a.label("puts")
    a.ld_a_hl(); a.or_a(); a.ret_z()
    a.call("putc"); a.inc_hl(); a.jr("puts")
    a.label("puthex")
    a.push_af()
    a.rrca(); a.rrca(); a.rrca(); a.rrca()
    a.call("nibble")
    a.pop_af()
    a.label("nibble")
    a.and_n(0x0F); a.add_a(0x90); a.daa(); a.adc_a(0x40); a.daa()
    a.jr("putc")

    a.label("s_exit"); a.text("EXIT\n\x04END\n")
    return a.assemble()


def disc(code: bytes) -> bytes:
    """Put the Z80 program on a CPC disc as DISC.BIN, loaded and started at Z80_LOAD."""
    image = DiskImage()
    image.add_file("DISC.BIN", code, load_addr=Z80_LOAD, exec_addr=Z80_LOAD)
    return image.to_dsk_bytes()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = sys.argv[1]
    with open(os.path.join(out, "demo.dsk"), "wb") as f:
        f.write(disc(z80_program()))
    with open(os.path.join(out, "demo.inc"), "w") as f:
        f.write(include())
    with open(os.path.join(out, "demo-palette.bin"), "wb") as f:
        f.write(palette())
    with open(os.path.join(out, "demo-patterns.bin"), "wb") as f:
        f.write(ball() + diamond())
    return 0


if __name__ == "__main__":
    sys.exit(main())
