#!/usr/bin/env python3
"""The proof-of-concept demo, end to end.

Runs work/demo.dsk on a CPC 6128 with work/demo.a16 on the serial port, three
times with the same scripted key presses. CPCEC boots to BASIC and types
RUN"DISC itself; the Z80 side sets RUN at about frame 157, and the 68000
program starts about 30 frames later, after the boot ROM has cleared memory.
All key and screenshot times below are counted from START. The first two runs
take one screenshot each, 60 frames apart; the third runs on past EXIT.
Checks:

  * the demo loads from disc, from BASIC,
  * the boot ROM loaded the 68000 program from the serial port,
  * the bitmap scrolls one pixel per frame,
  * holding CURSOR RIGHT for 30 frames moves the player's sprite 60 pixels,
  * SPACE makes the 68000 write the sound chip through the Z80, and switch the
    sound off again 10 frames later,
  * ESC makes the 68000 send EXIT and the Z80 hand the machine back: the CPC
    resets to the BASIC start-up screen.

    python3 tests/test_demo.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "demo"))
from test_video import read_png, rgb  # noqa: E402
import mkdemo  # noqa: E402

WORK = os.path.abspath(os.path.join(HERE, "..", "work"))

START = 160                      # frames: the demo's Z80 side has started by now
# frame:key:state. CURSOR RIGHT held for 30 frames, SPACE tapped, then ESC,
# released after the reset (else BASIC would see it and print *Break*).
KEYS = ",".join(f"{START + t}:{key}:{state}" for t, key, state in (
    (100, 1, 1), (130, 1, 0), (160, 47, 1), (170, 47, 0), (200, 66, 1), (220, 66, 0)))
BASIC_BLUE = (0, 0, 180)         # the firmware's background colour, as CPCEC draws it

EXPECT_SERIAL = "Arnold 16 boot ROM v0.3\nProgram loaded\n"
EXPECT_LOG = ("K0101\n"                      # CURSOR RIGHT down, sent to the 68000
              "K0100\n"                      # ... and up
              "K2F01\n"                      # SPACE down
              "A00FE\nA0100\nA073E\nA080F\n"  # the beep: tone, mixer, volume 15
              "A0800\n"                      # 10 frames later: volume 0
              "K2F00\n"                      # SPACE up
              "K4201\n"                      # ESC down
              "EXIT\n\x04END\n")


def run(shot_at: int, end_on_marker: bool = True) -> tuple[str, str, str, int]:
    tmp = tempfile.mkdtemp()
    shot, serial, printer = (os.path.join(tmp, n) for n in ("s.png", "ser.txt", "prn.txt"))
    result = subprocess.run(
        [os.path.join(WORK, "cpcec"), "--headless", "--arnold16",
         "--a16-serial-in", "demo.a16", "--a16-serial", serial,
         "--printer", printer, "--a16-keys", KEYS,
         "--shot", shot, "--shot-at", str(shot_at),
         *(["--end-on-marker"] if end_on_marker else []),
         "--max-frames", str(START + 400 if end_on_marker else shot_at + 1),
         "-m2", "demo.dsk"],
        cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=180, check=False)
    with open(serial, "rb") as f:
        sent = f.read().decode("ascii", "replace")
    with open(printer, "rb") as f:
        log = f.read().decode("ascii", "replace")
    return shot, sent, log, result.returncode


def main() -> int:
    for name in ("cpcec", "demo.dsk", "demo.a16"):
        if not os.path.exists(os.path.join(WORK, name)):
            print(f"no work/{name}: run ./fetch_build.sh first")
            return 2
    shot_a, serial, log, status = run(START + 90)
    shot_b, _, _, _ = run(START + 150)
    shot_c, _, _, _ = run(START + 360, end_on_marker=False)
    _, _, rows_c, bpp_c = read_png(shot_c)
    _, height, rows_a, bpp = read_png(shot_a)
    _, _, rows_b, _ = read_png(shot_b)
    rows_per_line = 2 if height >= 500 else 1
    left, top = 304 - 240, (144 - 68) // 2 * rows_per_line

    def pixel(rows: list[bytes], x: int, line: int) -> tuple[int, int, int]:
        at = (left + x * 2) * bpp
        return tuple(rows[top + line * rows_per_line][at:at + 3])

    yellow, navy = rgb(0xFE0), rgb(0x013)
    px, py = mkdemo.PLAYER_START
    moved = 30 * mkdemo.PLAYER_STEP
    checks = [
        ("boot ROM loaded the program from serial", serial == EXPECT_SERIAL),
        ("keys, sound and exit happened in order", log == EXPECT_LOG),
        ("the run ended on EXIT, not on the frame limit", status == 0),
        ("player's sprite starts in the middle",
         pixel(rows_a, px + 8, py + 8) == yellow),
        (f"CURSOR RIGHT moved it {moved} pixels",
         pixel(rows_b, px + moved + 8, py + 8) == yellow),
        ("... and it is no longer where it started",
         pixel(rows_b, px + 8, py + 8) != yellow),
        ("the bitmap is on screen", pixel(rows_a, 70, 70) != navy),
        ("after EXIT the CPC is back at the BASIC screen",
         all(tuple(rows_c[y][x * bpp_c:x * bpp_c + 3]) == BASIC_BLUE
             for x, y in ((20, 20), (400, 300), (700, 500)))),
    ]
    # 60 frames apart the bitmap has moved 60 pixels up and to the left
    for x, y in ((10, 10), (200, 60), (100, 120)):
        checks.append((f"bitmap scrolled 60 pixels in 60 frames, at ({x},{y})",
                       pixel(rows_b, x, y) == pixel(rows_a, x + 60, y + 60)))
    failed = 0
    for name, ok in checks:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if failed:
        print(f"serial: {serial!r}\nlog: {log!r}\nstatus: {status}")
        print(f"screenshots kept: {shot_a} {shot_b} {shot_c}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
