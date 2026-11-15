#!/usr/bin/env python3
"""The Arnold 16 video chip: bitmap, scrolling with wrap, palette, border,
sprites, and the frame and raster interrupts.

A 68000 test ROM (built here, loaded with --a16-rom) sets up one picture. A
Z80 cartridge programs the CRTC as the CPC firmware would, then starts the
68000 with the new display switched on. CPCEC saves a screenshot at frame 60
and this script checks single pixels in it.

    python3 tests/test_video.py [path/to/cpcec]

What the picture holds, and so what is checked:
  * Bitmap: every byte is the low 8 bits of its x position, plus one marker
    byte. With SCROLL_X=509 and SCROLL_Y=254 the window wraps in both
    directions, so screen pixel (3,0) shows bitmap (0,254) and the marker at
    bitmap (5,1) lands on screen pixel (8,3).
  * Sprites: number 0 and number 5 overlap (0 must be in front), number 1 is
    flipped, number 6 hangs off the left edge. Pattern 2 has a transparent
    first pixel in every row.
  * Interrupts: the frame interrupt sets the border green, the raster interrupt
    at line 100 sets it white. So the border is green above line 100 and white
    below it, which can only happen if both interrupts work.
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "asm"))
from z80 import Asm as Z80  # noqa: E402
from m68k import *  # noqa: E402,F403
from test_ping import cartridge  # noqa: E402

DEFAULT_EMU = os.path.join(HERE, "..", "work", "cpcec")

# 68000 addresses, from the hardware spec
VRAM = 0xE00000
PATTERNS = 0xE20000
VID_CTRL, VID_STAT, SCROLL_X, SCROLL_Y = 0xFF0000, 0xFF0002, 0xFF0004, 0xFF0006
RASTER_LINE, BORDER = 0xFF0008, 0xFF000C
SPRITES, PALETTE = 0xFF0100, 0xFF0200
VECTOR_RASTER, VECTOR_FRAME = 0x70, 0x78   # autovectors, levels 4 and 6

# palette entries used by the test: index -> 0RGB
COLOURS = {0: 0x888, 1: 0xFFF, 3: 0xF00, 4: 0x00F, 5: 0x0F0, 6: 0xFF0, 7: 0x0FF}
BLACK = 0x000


def rgb(c: int) -> tuple[int, int, int]:
    """A 12-bit 0RGB colour as the 24-bit colour the screenshot should hold."""
    return ((c >> 8) * 17, ((c >> 4) & 15) * 17, (c & 15) * 17)


def test_rom() -> bytes:
    a = Asm(org=0xF00000)
    a.l(0x100000)
    a.l("start")
    a.label("start")

    # bitmap: 128 KB, each byte = low 8 bits of its address = its x position & 255
    a.lea(absl(VRAM), A0)
    a.move("l", imm(0x20000 - 1), D1)
    a.label("fill")
    a.move("w", A0, D0)
    a.move("b", D0, inc(A0))
    a.subq("l", 1, D1)
    a.bpl("fill")
    a.move("b", imm(6), absl(VRAM + 1 * 512 + 5))    # the marker: bitmap (5,1) = colour 6

    # sprite patterns: 2 = all colour 7 with a transparent first pixel per row,
    # 3 = all colour 4
    a.lea(absl(PATTERNS + 2 * 256), A0)
    a.moveq(15, D1)
    a.label("pattern2_row")
    a.clr("b", inc(A0))
    a.moveq(14, D0)
    a.label("pattern2_pixel")
    a.move("b", imm(7), inc(A0))
    a.dbra(D0, "pattern2_pixel")
    a.dbra(D1, "pattern2_row")
    a.move("w", imm(255), D0)                        # pattern 3 follows pattern 2
    a.label("pattern3")
    a.move("b", imm(4), inc(A0))
    a.dbra(D0, "pattern3")

    for index, colour in COLOURS.items():
        a.move("w", imm(colour), absl(PALETTE + index * 2))

    def sprite(n: int, x: int, y: int, pattern: int, flags: int) -> None:
        base = SPRITES + n * 8
        a.move("w", imm(x), absl(base))
        a.move("w", imm(y), absl(base + 2))
        a.move("w", imm((pattern << 8) | flags), absl(base + 4))

    sprite(0, 100, 50, 2, 1)       # visible
    sprite(1, 200, 50, 2, 3)       # visible, flipped left to right
    sprite(5, 108, 50, 3, 1)       # overlaps sprite 0 by 8 pixels
    sprite(6, -8, 100, 3, 1)       # half off the left edge

    a.move("w", imm(509), absl(SCROLL_X))
    a.move("w", imm(254), absl(SCROLL_Y))
    a.move("w", imm(100), absl(RASTER_LINE))
    a.move("l", imm("raster"), absl(VECTOR_RASTER))
    a.move("l", imm("frame"), absl(VECTOR_FRAME))
    a.move("w", imm(0x000F), absl(VID_CTRL))   # display, sprites, frame and raster interrupts
    a.label("idle")
    a.stop(0x2000)
    a.bra("idle")

    a.label("frame")                     # level 6: the picture has ended
    a.tst("w", absl(VID_STAT))           # reading it drops the interrupt
    a.move("w", imm(5), absl(BORDER))    # green
    a.rte()

    a.label("raster")                    # level 4: line 100 starts
    a.tst("w", absl(VID_STAT))
    a.move("w", imm(1), absl(BORDER))    # white
    a.rte()

    return a.assemble().ljust(0x10000, b"\xFF")


# the CRTC values the CPC firmware sets for a 50 Hz screen, registers 0 to 13
CRTC = (63, 40, 46, 142, 38, 0, 25, 30, 0, 7, 0, 0, 48, 0)


def z80_program() -> bytes:
    a = Z80(org=0)
    a.di()
    a.ld_sp(0xC000)
    for register, value in enumerate(CRTC):
        a.ld_bc(0xBC00); a.ld_a(register); a.out_c_a()
        a.ld_bc(0xBD00); a.ld_a(value); a.out_c_a()
    a.ld_bc(0xF9E1); a.ld_a(3); a.out_c_a()      # CTRL: RUN + DISPLAY
    a.label("stop"); a.jr("stop")
    return a.assemble()


def read_png(path: str) -> tuple[int, int, list[bytes], int]:
    """A minimal PNG reader: 8-bit RGB or RGBA, not interlaced."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    at, idat, width, height, bpp = 8, b"", 0, 0, 3
    while at < len(data):
        size, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + size]
        at += 12 + size
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or colour not in (2, 6) or interlace:
                raise ValueError("unsupported PNG format")
            bpp = 3 if colour == 2 else 4
        elif kind == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride = width * bpp
    rows: list[bytes] = []
    previous = bytearray(stride)
    for y in range(height):
        kind = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                best = left if pa <= pb and pa <= pc else up if pb <= pc else corner
                line[i] = (line[i] + best) & 255
        rows.append(bytes(line))
        previous = line
    return width, height, rows, bpp


def main() -> int:
    emu = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMU)
    if not os.path.exists(emu):
        print(f"no emulator at {emu}: run ./fetch_build.sh first")
        return 2
    tmp = tempfile.mkdtemp()
    cpr, rom, shot = (os.path.join(tmp, n) for n in ("t.cpr", "t.rom", "t.png"))
    with open(cpr, "wb") as f:
        f.write(cartridge(z80_program()))
    with open(rom, "wb") as f:
        f.write(test_rom())
    subprocess.run([emu, "--headless", "--arnold16", "--a16-rom", rom,
                    "--shot", shot, "--shot-at", "60", "--max-frames", "62",
                    "-m3", cpr],
                   cwd=os.path.dirname(emu), stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120, check=False)
    if not os.path.exists(shot):
        print("FAIL  no screenshot was saved")
        return 1
    width, height, rows, bpp = read_png(shot)

    # CPCEC's screenshot is 768 units wide and shows the frame from unit 240
    # across and unit 68 down; the Arnold 16 picture starts at unit 304 across
    # and 144 down, and each of its pixels is 2 units each way. The shot may
    # hold one row per scan line (half height) or two.
    rows_per_line = 2 if height >= 500 else 1
    left = 304 - 240
    top = (144 - 68) // 2 * rows_per_line

    def pixel(x: int, line: int) -> tuple[int, int, int]:
        """Screen pixel x (0-319) on picture line `line` (0-199)."""
        row = rows[top + line * rows_per_line]
        at = (left + x * 2) * bpp
        return tuple(row[at:at + 3])

    def border(line: int) -> tuple[int, int, int]:
        row = rows[top + line * rows_per_line]
        return tuple(row[8 * bpp:8 * bpp + 3])

    checks = [
        # bitmap, scrolled and wrapped: screen x shows bitmap x+509 (mod 512)
        ("bitmap wraps across: screen (3,0) is bitmap x=0", pixel(3, 0), COLOURS[0]),
        ("bitmap: screen (4,0) is bitmap x=1", pixel(4, 0), COLOURS[1]),
        ("bitmap: screen (6,0) is bitmap x=3", pixel(6, 0), COLOURS[3]),
        ("bitmap: an unset palette entry is black", pixel(20, 0), BLACK),
        ("bitmap wraps down: marker at screen (8,3)", pixel(8, 3), COLOURS[6]),
        ("bitmap: no marker one line up", pixel(8, 2), COLOURS[5]),
        # sprites
        ("sprite 0: first pixel is transparent", pixel(100, 50), BLACK),
        ("sprite 0: second pixel is drawn", pixel(101, 50), COLOURS[7]),
        ("sprite 0: last row is line 65", pixel(107, 65), COLOURS[7]),
        ("sprite 0: nothing on line 66", pixel(107, 66), BLACK),
        ("sprite 0 is in front of sprite 5", pixel(112, 50), COLOURS[7]),
        ("sprite 5 shows beside sprite 0", pixel(120, 50), COLOURS[4]),
        ("sprite 1 flipped: first pixel is drawn", pixel(200, 50), COLOURS[7]),
        ("sprite 1 flipped: last pixel is transparent", pixel(215, 50), BLACK),
        ("sprite 6 is clipped at the left edge", pixel(0, 100), COLOURS[4]),
        ("sprite 6 ends at x=7: bitmap shows at x=8", pixel(8, 100), COLOURS[5]),
        # interrupts, seen through the border colour
        ("frame interrupt: border is green on line 50", border(50), COLOURS[5]),
        ("raster interrupt: border is white on line 150", border(150), COLOURS[1]),
        ("raster interrupt takes effect on its own line: 99 is green", border(99), COLOURS[5]),
        ("raster interrupt takes effect on its own line: 100 is white", border(100), COLOURS[1]),
        ("frame interrupt comes when the picture ends: 199 is white", border(199), COLOURS[1]),
        ("frame interrupt comes when the picture ends: 200 is green", border(200), COLOURS[5]),
    ]
    failed = 0
    for name, got, want in checks:
        ok = got == rgb(want)
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}"
              + ("" if ok else f"  (wanted {rgb(want)}, got {got})"))
    if failed:
        print(f"screenshot kept at {shot} ({width}x{height})")
    else:
        for path in (cpr, rom, shot):
            os.unlink(path)
        os.rmdir(tmp)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
