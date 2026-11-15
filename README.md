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

Steps 1 to 3 of 4 are done.

| Step | What | State |
| --- | --- | --- |
| 1 | Z80 ports `&F9E0` to `&F9E7` and the mailbox | Done, tested |
| 2 | 68000 core with 1 MB RAM, boot ROM and debug serial output | Done, tested |
| 3 | PING answered by 68000 code in the boot ROM, through the mailbox interrupt | Done, tested |
| 4 | New video chip: bitmap, scrolling, sprites | Not started |

Not built yet: the video chip (its RAM is plain memory, its registers read as
zero), serial input, and the KEY, AY_WRITE and EXIT mailbox commands.

## Build and test

Needs git, a C compiler, SDL2 and Python 3.

    brew install sdl2            # macOS
    sudo apt install libsdl2-dev # Ubuntu

    make test

`make` fetches CPCEC and Musashi, applies the patches, builds `work/cpcec` and
the boot ROM `work/arnold16.rom`. `make test` then runs a real Z80 program
that starts the 68000 and sends PING through the mailbox. It checks that the
boot ROM printed its banner on the serial port and answered, and that with
Arnold 16 switched off the machine is a plain CPC.

## Running it

    work/cpcec --arnold16            # a CPC 6128 with the Arnold 16 hardware
    work/cpcec                       # unchanged CPCEC

| Option | Effect |
| --- | --- |
| `--arnold16` | Switch the Arnold 16 hardware on |
| `--a16-rom FILE` | Use this 68000 boot ROM instead of `arnold16.rom` beside the emulator |
| `--a16-serial FILE` | Write the 68000's debug serial output to FILE |

Without `--arnold16` the emulator behaves as upstream CPCEC. The 68000 only
starts when a Z80 program sets the RUN bit, so nothing visible happens until
then.

## What is in the repo

| Path | What |
| --- | --- |
| `fetch_build.sh` | Fetches CPCEC at the pinned commit, applies `patches/` in order, builds |
| `patches/0001-cpcbuild-headless.patch` | Options for unattended test runs (`--headless`, `--printer`, `--max-frames`, ...). Copied from [CPCBuild](https://github.com/carcharo/cpcbuild) `tools/cpcec`. |
| `patches/0002-arnold16.patch` | The Arnold 16 hardware. Adds `cpcec-a16.h` and a few hook lines in `cpcec.c`. |
| `rom/mkboot.py` | Builds the 68000 boot ROM |
| `rom/m68k.py` | A very small 68000 assembler used by `mkboot.py` |
| `tests/test_ping.py` | The ports, mailbox and boot ROM test |
| `tests/z80.py` | A very small Z80 assembler used by the tests |

## Changing the emulator

Edit the files under `work/src` (after a build they are the patched CPCEC
sources), rebuild with the `cc` line from `fetch_build.sh`, and when it works
regenerate `patches/0002-arnold16.patch`. It must hold only the Arnold 16
changes, so take the difference against a tree that has patch 0001 applied:

    cd work/src
    git stash -u                      # set your edits aside
    git apply ../../patches/0001-cpcbuild-headless.patch
    git add -A && git commit -qm "patch 0001"
    git stash pop                     # bring your edits back
    git add cpcec.c cpcec-a16.h
    git diff --cached > ../../patches/0002-arnold16.patch

Careful: `fetch_build.sh` resets `work/src` to the clean pinned commit every
time, so save the patch before running `make` again.

CPCEC's sources use Windows line endings. Editors and scripts must keep them,
or the patch will rewrite every line.

## Licence

GPL-3.0, the same as CPCEC, which this work derives from. CPCEC is
copyright César Nicolás-González. Musashi is copyright Karl Stenerud and
under the MIT licence, which is compatible with GPL-3.0.
