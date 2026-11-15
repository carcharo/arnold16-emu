# arnold16-emu

The emulator for Arnold 16, a "what if" 16-bit successor to the Amstrad CPC: a
complete CPC with a 68000 machine beside it. This is the reference
implementation of the hardware spec; the FPGA version must match it.

It is [CPCEC](http://cngsoft.no-ip.org/cpcec.htm) by César Nicolás-González
at a pinned commit, plus a small set of patches. CPCEC's source and ROMs are
not kept in this repo: the build script fetches them.

## Status

Step 1 of 4 is done.

| Step | What | State |
| --- | --- | --- |
| 1 | Z80 ports `&F9E0` to `&F9E7` and the mailbox. A stand-in answers PING in place of the 68000. | Done, tested |
| 2 | 68000 core, boot ROM and debug serial port | Not started |
| 3 | PING answered by real 68000 code | Not started |
| 4 | New video chip: bitmap, scrolling, sprites | Not started |

## Build and test

Needs git, a C compiler, SDL2 and Python 3.

    brew install sdl2            # macOS
    sudo apt install libsdl2-dev # Ubuntu

    make test

`make` fetches CPCEC, applies the patches and builds `work/cpcec`. `make test`
then runs a real Z80 program in it that sends PING through the mailbox and
checks the reply, once with Arnold 16 switched on and once as a plain CPC.

## Running it

    work/cpcec --arnold16            # a CPC 6128 with the Arnold 16 hardware
    work/cpcec                       # unchanged CPCEC

Without `--arnold16` the emulator behaves exactly as upstream CPCEC.

## What is in the repo

| Path | What |
| --- | --- |
| `fetch_build.sh` | Fetches CPCEC at the pinned commit, applies `patches/` in order, builds |
| `patches/0001-cpcbuild-headless.patch` | Options for unattended test runs (`--headless`, `--printer`, `--max-frames`, ...). Copied from [CPCBuild](https://github.com/carcharo/cpcbuild) `tools/cpcec`. |
| `patches/0002-arnold16-ports-mailbox.patch` | The Arnold 16 hardware. Adds `cpcec-a16.h` and six hook lines in `cpcec.c`. |
| `tests/test_ping.py` | The step 1 test |
| `tests/z80.py` | A very small Z80 assembler used by the tests |

## Changing the emulator

Edit the files under `work/src` (after a build they are the patched CPCEC
sources), rebuild with the `cc` line from `fetch_build.sh`, and when it works
regenerate the patch:

    cd work/src
    git add cpcec.c cpcec-a16.h
    git diff --cached > ../../patches/0002-arnold16-ports-mailbox.patch

Careful: `fetch_build.sh` resets `work/src` to the clean pinned commit every
time, so save the patch before running `make` again.

CPCEC's sources use Windows line endings. Editors and scripts must keep them,
or the patch will rewrite every line.

## Licence

GPL-3.0, the same as CPCEC, which this work derives from. CPCEC is
copyright César Nicolás-González.
