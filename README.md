# arnold16-emu

The emulator for Arnold 16, a "what if" 16-bit successor to the Amstrad CPC: a
complete CPC with a 68000 machine beside it. This is the reference
implementation of the hardware spec; the FPGA version must match it.

It is [CPCEC](http://cngsoft.no-ip.org/cpcec.htm) by César Nicolás-González
at a pinned commit, plus a small set of patches, linked with the
[Musashi](https://github.com/kstenerud/Musashi) 68000 core by Karl Stenerud.
Neither project's source, nor CPCEC's ROMs, are kept in this repo: the build
script fetches them.

## Status

The emulator runs the proof-of-concept demo: a 68000 program, loaded by the
boot ROM, scrolls a 256-colour bitmap under four sprites. The cursor keys
steer the ball, SPACE beeps, ESC hands the machine back to the CPC.

![The demo](docs/demo.png)

    make demo

| Step | What | State |
| --- | --- | --- |
| 1 | Z80 ports `&F9E0` to `&F9E7` and the mailbox | Done, tested |
| 2 | 68000 core with 1 MB RAM, boot ROM and debug serial output | Done, tested |
| 3 | PING answered by 68000 code in the boot ROM, through the mailbox interrupt | Done, tested |
| 4 | Video chip: 320 x 200 window on a 512 x 256 bitmap in 256 colours, scrolling, 32 sprites, frame and raster interrupts | Done, tested |

| 5 | Serial input and a boot ROM that loads a 68000 program from it | Done, tested |
| 6 | The demo: keyboard, sound and exit through the mailbox (KEY, AY_WRITE, EXIT) | Done, tested |

Not done yet:

- Starting the demo from CPC BASIC. For now the Z80 side is a Plus cartridge
  that starts the 68000 at once.
- Seeing or hearing it on a real screen: every test so far is headless. The
  beep is checked by what is written to the sound chip, not by ear.
- Running any of this on a Mac.

## Build and test

Needs git, a C compiler, SDL2 and Python 3.

    brew install sdl2            # macOS
    sudo apt install libsdl2-dev # Ubuntu

    make test

`make` fetches CPCEC and Musashi, applies the patches, and builds `work/cpcec`,
the boot ROM `work/arnold16.rom` and the demo (`work/demo.cpr`,
`work/demo.a16`).

`make test` runs four tests:

| Test | What it checks |
| --- | --- |
| `tests/test_asm.py` | The Python 68000 assembler, against Musashi's disassembler |
| `tests/test_ping.py` | Ports, mailbox and boot ROM: a Z80 program sends PING, the 68000 answers |
| `tests/test_video.py` | The video chip: a 68000 test ROM draws a picture; single pixels of a screenshot are checked |
| `tests/test_demo.py` | The demo end to end, with scripted key presses |

## Running it

    work/cpcec --arnold16            # a CPC 6128 with the Arnold 16 hardware
    work/cpcec                       # unchanged CPCEC

| Option | Effect |
| --- | --- |
| `--arnold16` | Switch the Arnold 16 hardware on |
| `--a16-rom FILE` | Use this 68000 boot ROM instead of `arnold16.rom` beside the emulator |
| `--a16-serial FILE` | Write the 68000's debug serial output to FILE |
| `--a16-serial-in FILE` | Feed FILE to the 68000's serial port. The boot ROM loads a program from it. |
| `--a16-keys LIST` | For tests: press and release CPC keys at given frames, as `FRAME:KEY:STATE,...` |

To run your own 68000 program, wrap it with `tools/mkload.py` and pass it with
`--a16-serial-in`. The boot ROM waits for the four bytes `A16L`, then a load
address and a length (4 bytes each, high byte first), copies that many bytes
to the address and jumps there. The program starts in supervisor mode with
interrupts allowed. It must take over the mailbox interrupt (level 2), because
the Z80 side waits for each KEY message to be read.

Without `--arnold16` the emulator behaves as upstream CPCEC. The 68000 only
starts when a Z80 program sets the RUN bit, so nothing visible happens until
then.

## What is in the repo

| Path | What |
| --- | --- |
| `fetch_build.sh` | Fetches CPCEC at the pinned commit, applies `patches/` in order, builds |
| `patches/0001-cpcbuild-headless.patch` | Options for unattended test runs (`--headless`, `--printer`, `--max-frames`, ...). Copied from [CPCBuild](https://github.com/carcharo/cpcbuild) `tools/cpcec`. |
| `patches/0002-arnold16.patch` | The Arnold 16 hardware. Adds `cpcec-a16.h` and a few hook lines in `cpcec.c`. |
| `tools/mkpatch.sh` | Regenerates `patches/0002-arnold16.patch` from `work/src` |
| `tools/mkload.py` | Wraps a 68000 program for the boot ROM's serial loader |
| `tools/dis68k.c` | A disassembler built from Musashi, used to test the assembler |
| `rom/mkboot.py` | Builds the 68000 boot ROM |
| `demo/mkdemo.py` | Builds the demo: the 68000 program and the Z80 cartridge that serves it |
| `asm/m68k.py` | A small 68000 assembler in Python |
| `asm/z80.py` | A very small Z80 assembler in Python |
| `tests/` | The four tests. `test_video.py` and `demo/mkdemo.py` are worked examples of driving the hardware. |

## Changing the emulator

Edit the files under `work/src` (after a build they are the patched CPCEC
sources), rebuild with the `cc` line from `fetch_build.sh`, and when it works
regenerate the patch:

    sh tools/mkpatch.sh

`fetch_build.sh` resets `work/src` to the clean pinned commit every time. It
stops first if `work/src` holds edits that are not in the patch yet.

The 68000 and Z80 code is written with the two small Python assemblers in
`asm/`, so that nothing but Python is needed to build. They cover only what
has been needed so far. A real assembler would be the better tool once there
is more 68000 code than this.

CPCEC's sources use Windows line endings. Editors and scripts must keep them,
or the patch will rewrite every line.

## Licence

GPL-3.0, the same as CPCEC, which this work derives from. CPCEC is
copyright César Nicolás-González. Musashi is copyright Karl Stenerud and
under the MIT licence, which is compatible with GPL-3.0.
