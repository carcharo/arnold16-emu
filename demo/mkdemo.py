#!/usr/bin/env python3
"""Builds the Arnold 16 proof-of-concept demo.

    python3 demo/mkdemo.py work

writes two files into the directory given:
  demo.cpr   a Plus cartridge holding the Z80 side
  demo.a16   the 68000 program, wrapped for the boot ROM's serial loader

Run it with
    work/cpcec --arnold16 --a16-serial-in work/demo.a16 -m3 work/demo.cpr

The Z80 side programs the CRTC, starts the 68000 with the new display on, and
then serves it for ever: it scans the keyboard and sends a KEY message for
every key that goes down or up, writes the AY sound chip when asked
(AY_WRITE), and hands the machine back to the CPC on EXIT. It also logs what
it does to the printer port, which the tests read.

The 68000 side fills the 512 x 256 bitmap with a pattern, scrolls it one pixel
per frame, moves three sprites across it, and lets the cursor keys steer a
fourth. SPACE plays a short beep. ESC ends the demo.
"""
from __future__ import annotations

import colorsys
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from m68k import *  # noqa: E402,F403
from z80 import Asm as Z80  # noqa: E402
from mkload import wrap  # noqa: E402

# --- hardware, from the spec ------------------------------------------------
PORT_CTRL, PORT_STATUS, PORT_CMD, PORT_DATA = 0xF9E1, 0xF9E2, 0xF9E3, 0xF9E4
VRAM, PATTERNS = 0xE00000, 0xE20000
VID_CTRL, VID_STAT, SCROLL_X, SCROLL_Y, BORDER = 0xFF0000, 0xFF0002, 0xFF0004, 0xFF0006, 0xFF000C
SPRITES, PALETTE = 0xFF0100, 0xFF0200
MBOX_CMD, MBOX_STAT, MBOX_DATA = 0xFF1001, 0xFF1003, 0xFF1004
VECTOR_MAILBOX, VECTOR_FRAME = 0x68, 0x78
CMD_KEY, CMD_AY_WRITE, CMD_EXIT = 1, 2, 3

# CPC key numbers
KEY_UP, KEY_RIGHT, KEY_DOWN, KEY_LEFT, KEY_SPACE, KEY_ESC = 0, 1, 2, 8, 47, 66

LOAD_ADDRESS = 0x1000
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


# --- the 68000 program ------------------------------------------------------
# variables, in RAM below the program
V_TICK, V_EXIT, V_BEEP, V_BEEP_TIMER = 0x800, 0x801, 0x802, 0x803
V_KEY_UP, V_KEY_RIGHT, V_KEY_DOWN, V_KEY_LEFT = 0x804, 0x805, 0x806, 0x807
V_SCROLL, V_PLAYER_X, V_PLAYER_Y = 0x808, 0x80A, 0x80C
V_DRIFT = 0x810                 # three words: where sprites 1 to 3 are, 0-511


def program() -> bytes:
    a = Asm(org=LOAD_ADDRESS)
    a.move_to_sr(0x2700)                               # no interrupts while setting up

    # variables
    a.lea(absl(V_TICK), A0)
    a.moveq(15, D0)
    a.label("clear_vars")
    a.clr("w", inc(A0))
    a.dbra(D0, "clear_vars")
    a.move("w", imm(PLAYER_START[0]), absl(V_PLAYER_X))
    a.move("w", imm(PLAYER_START[1]), absl(V_PLAYER_Y))
    a.move("w", imm(0), absl(V_DRIFT))
    a.move("w", imm(170), absl(V_DRIFT + 2))
    a.move("w", imm(340), absl(V_DRIFT + 4))

    # palette and sprite patterns, copied from the tables at the end
    a.lea(pc("palette"), A0)
    a.lea(absl(PALETTE), A1)
    a.move("w", imm(255), D0)
    a.label("copy_palette")
    a.move("w", inc(A0), inc(A1))
    a.dbra(D0, "copy_palette")
    a.lea(pc("patterns"), A0)
    a.lea(absl(PATTERNS), A1)
    a.move("w", imm(511), D0)
    a.label("copy_patterns")
    a.move("b", inc(A0), inc(A1))
    a.dbra(D0, "copy_patterns")

    # bitmap: each pixel is x XOR y, a pattern that looks the same wherever it wraps
    a.lea(absl(VRAM), A1)
    a.moveq(0, D3)                                     # y
    a.label("fill_row")
    a.moveq(0, D2)                                     # x
    a.label("fill_pixel")
    a.move("b", D2, D0)
    a.eor("b", D3, D0)
    a.move("b", D0, inc(A1))
    a.addq("w", 1, D2)
    a.cmp("w", imm(512), D2)
    a.bne("fill_pixel")
    a.addq("w", 1, D3)
    a.cmp("w", imm(256), D3)
    a.bne("fill_row")

    # sprites: 0 is the player (pattern 0), 1 to 3 drift across (pattern 1)
    a.move("w", imm(0x0001), absl(SPRITES + 4))        # pattern 0, visible
    for n, y in ((1, 30), (2, 100), (3, 160)):
        a.move("w", imm(y), absl(SPRITES + n * 8 + 2))
        a.move("w", imm(0x0101), absl(SPRITES + n * 8 + 4))   # pattern 1, visible

    a.move("w", imm(NAVY), absl(BORDER))
    a.move("l", imm("mailbox"), absl(VECTOR_MAILBOX))
    a.move("l", imm("frame"), absl(VECTOR_FRAME))
    a.move("w", imm(0x0007), absl(VID_CTRL))           # display, sprites, frame interrupt

    # --- main loop: sleep until the frame interrupt, then move everything ----
    a.label("main")
    a.stop(0x2000)
    a.tst("b", absl(V_TICK))
    a.beq("main")
    a.clr("b", absl(V_TICK))

    a.tst("b", absl(V_EXIT))                           # ESC was pressed: hand back to the CPC
    a.beq("no_exit")
    a.moveq(CMD_EXIT, D0)
    a.moveq(0, D1)
    a.bsr("send")
    a.label("halt")                                    # the Z80 will put us in reset
    a.stop(0x2700)
    a.bra("halt")
    a.label("no_exit")

    # scroll one pixel down and to the right per frame
    a.addq("w", 1, absl(V_SCROLL))
    a.move("w", absl(V_SCROLL), D0)
    a.and_("w", imm(511), D0)
    a.move("w", D0, absl(SCROLL_X))
    a.and_("w", imm(255), D0)
    a.move("w", D0, absl(SCROLL_Y))

    # the player's sprite follows the cursor keys and stays on screen
    a.tst("b", absl(V_KEY_LEFT))
    a.beq("not_left")
    a.sub("w", imm(PLAYER_STEP), absl(V_PLAYER_X))
    a.bpl("not_left")
    a.clr("w", absl(V_PLAYER_X))
    a.label("not_left")
    a.tst("b", absl(V_KEY_RIGHT))
    a.beq("not_right")
    a.add("w", imm(PLAYER_STEP), absl(V_PLAYER_X))
    a.cmp("w", imm(304), absl(V_PLAYER_X))
    a.bls("not_right")
    a.move("w", imm(304), absl(V_PLAYER_X))
    a.label("not_right")
    a.tst("b", absl(V_KEY_UP))
    a.beq("not_up")
    a.sub("w", imm(PLAYER_STEP), absl(V_PLAYER_Y))
    a.bpl("not_up")
    a.clr("w", absl(V_PLAYER_Y))
    a.label("not_up")
    a.tst("b", absl(V_KEY_DOWN))
    a.beq("not_down")
    a.add("w", imm(PLAYER_STEP), absl(V_PLAYER_Y))
    a.cmp("w", imm(184), absl(V_PLAYER_Y))
    a.bls("not_down")
    a.move("w", imm(184), absl(V_PLAYER_Y))
    a.label("not_down")
    a.move("w", absl(V_PLAYER_X), absl(SPRITES))
    a.move("w", absl(V_PLAYER_Y), absl(SPRITES + 2))

    # sprites 1 to 3 drift right at different speeds and come round again
    for n, speed in ((1, 1), (2, 2), (3, 3)):
        var = V_DRIFT + (n - 1) * 2
        a.move("w", absl(var), D0)
        a.addq("w", speed, D0)
        a.and_("w", imm(511), D0)
        a.move("w", D0, absl(var))
        a.sub("w", imm(96), D0)                        # 0-511 becomes -96 to 415
        a.move("w", D0, absl(SPRITES + n * 8))

    # sound: SPACE starts a beep, which is switched off some frames later
    a.tst("b", absl(V_BEEP))
    a.beq("no_beep")
    a.clr("b", absl(V_BEEP))
    for register, value in ((0, 0xFE), (1, 0x00), (7, 0x3E), (8, 0x0F)):
        a.move("l", imm((register << 24) | (value << 16)), D1)
        a.moveq(CMD_AY_WRITE, D0)
        a.bsr("send")
    a.move("b", imm(BEEP_FRAMES), absl(V_BEEP_TIMER))
    a.label("no_beep")
    a.tst("b", absl(V_BEEP_TIMER))
    a.beq("main")
    a.subq("b", 1, absl(V_BEEP_TIMER))
    a.bne("main")
    a.move("l", imm(8 << 24), D1)                      # volume of channel A to 0
    a.moveq(CMD_AY_WRITE, D0)
    a.bsr("send")
    a.bra("main")

    a.label("send")                # send command D0 with data D1 to the Z80
    a.btst(1, absl(MBOX_STAT))     # wait until it has taken the last message
    a.bne("send")
    a.move("l", D1, absl(MBOX_DATA))
    a.move("b", D0, absl(MBOX_CMD))
    a.rts()

    # --- interrupts -------------------------------------------------------
    a.label("frame")               # level 6: the picture has ended
    a.tst("w", absl(VID_STAT))     # reading it drops the interrupt
    a.move("b", imm(1), absl(V_TICK))
    a.rte()

    a.label("mailbox")             # level 2: a message from the Z80
    a.move("l", D0, dec(SP))
    a.move("l", D1, dec(SP))
    a.move("l", absl(MBOX_DATA), D1)
    a.move("b", absl(MBOX_CMD), D0)
    a.cmp("b", imm(CMD_KEY), D0)
    a.bne("mailbox_done")
    a.swap(D1)                     # low word is now: key number, then 1 = down
    a.move("w", D1, D0)
    a.lsr("w", 8, D0)              # D0 = key number
    a.and_("w", imm(1), D1)        # D1 = 1 if down
    for key, var in ((KEY_UP, V_KEY_UP), (KEY_RIGHT, V_KEY_RIGHT),
                     (KEY_DOWN, V_KEY_DOWN), (KEY_LEFT, V_KEY_LEFT)):
        a.cmp("b", imm(key), D0)
        a.bne(f"not_key_{key}")
        a.move("b", D1, absl(var))
        a.bra("mailbox_done")
        a.label(f"not_key_{key}")
    a.tst("b", D1)                 # the rest act only when pressed
    a.beq("mailbox_done")
    a.cmp("b", imm(KEY_SPACE), D0)
    a.bne("not_space")
    a.move("b", imm(1), absl(V_BEEP))
    a.label("not_space")
    a.cmp("b", imm(KEY_ESC), D0)
    a.bne("mailbox_done")
    a.move("b", imm(1), absl(V_EXIT))
    a.label("mailbox_done")
    a.move("l", inc(SP), D1)
    a.move("l", inc(SP), D0)
    a.rte()

    # --- tables -----------------------------------------------------------
    a.label("palette")
    a.data(palette())
    a.label("patterns")
    a.data(ball() + diamond())
    return a.assemble()


# --- the Z80 side -----------------------------------------------------------
# the CRTC values the CPC firmware sets for a 50 Hz screen, registers 0 to 13
CRTC = (63, 40, 46, 142, 38, 0, 25, 30, 0, 7, 0, 0, 48, 0)
PRINTER = 0xEF00
Z_LINE = 0x8100                 # variable: keyboard line being scanned
Z_PREVIOUS = 0x8000             # ten bytes: the keyboard lines as last seen


def z80_program() -> bytes:
    a = Z80(org=0)
    a.di()
    a.ld_sp(0xC000)
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
    a.label("stop"); a.jr("stop")                   # a real loader would return to BASIC here

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


def cartridge(code: bytes) -> bytes:
    """Wrap a Z80 program as a one-page Plus cartridge (.cpr, a RIFF file)."""
    page = code.ljust(16384, b"\0")
    body = b"AMS!" + b"cb00" + struct.pack("<I", len(page)) + page
    return b"RIFF" + struct.pack("<I", len(body)) + body


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = sys.argv[1]
    with open(os.path.join(out, "demo.cpr"), "wb") as f:
        f.write(cartridge(z80_program()))
    with open(os.path.join(out, "demo.a16"), "wb") as f:
        f.write(wrap(program(), LOAD_ADDRESS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
