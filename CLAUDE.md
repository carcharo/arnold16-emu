# arnold16-emu: brief for AI sessions

Read `README.md` first. The hardware this emulates is defined in the private
repo `carcharo/arnold16-docs`, file `spec/hardware-spec-v0.3.md`. The spec is
the authority: if the code and the spec disagree, stop and ask which is right.
Project status and next steps are in that repo's `STATUS.md`; update it at the
end of a session.

## Rules

- Never commit CPCEC's source or ROM files. Only patches go in this repo.
  `work/` is git-ignored.
- Everything Arnold 16 adds must be inert without `--arnold16`, so plain
  CPCEC behaviour is unchanged and existing CPC software still runs.
- Keep Arnold 16 code in `cpcec-a16.h`. Touch `cpcec.c` only for one-line
  hooks, so the patch survives upstream changes.
- CPCEC sources have CRLF line endings. Preserve them when editing or
  scripting changes, and check `git diff --stat` shows only the lines meant.
- Every change ships with a test in `tests/` that runs real Z80 (later 68000)
  code headless and checks its output. `make test` must pass from a clean
  checkout (`make clean && make test`) before committing.
- `fetch_build.sh` wipes `work/src` back to the pinned commit. Run
  `sh tools/mkpatch.sh` after every edit there, before any `make`. The script
  refuses to wipe unsaved edits, but do not rely on it.
- Licence is GPL-3.0. Anything added (for example a 68000 core) must be
  GPL-compatible; check and record its licence before adding it.
- Git: work on `main` unless asked otherwise. Explain any git step that is not
  a plain commit and push.

## Layout of the emulated hardware in code

- Ports: `a16_send()` and `a16_recv()` in `cpcec-a16.h`, called from
  `z80_send()` and `z80_recv()` in `cpcec.c`.
- Per-step work: `a16_main(t)`, called from `z80_sync()`. This is where the
  68000 will be stepped.
- Reset: `a16_reset()`, called from `all_reset()`.
- 68000: Musashi, pinned in `fetch_build.sh`, MIT licence. Its memory map is
  the `m68k_read_memory_8()` and `m68k_write_memory_8()` callbacks in
  `cpcec-a16.h`. It runs 8 cycles per CPCEC tick: CPCEC counts time in
  microseconds, not Z80 clock cycles.
- Video chip: `a16_scanline()`, called from `video_main()` when the CPC ends a
  scan line. It draws the line over the CPC's picture (`a16_draw()`), counts
  lines and raises the frame and raster interrupts. Registers, sprite table
  and palette are in the memory callbacks.
- Interrupt levels: frame 6, raster 4, mailbox 2; `a16_irq()` picks the
  highest that is pending and enabled.
  Frame and raster are acknowledged by writing 1 to their VID_STAT bit;
  reading VID_STAT changes nothing.
- RAM and video RAM start full of junk (`a16_start()`), as on real hardware.
  The boot ROM clears them, so test ROMs that skip the boot ROM must not
  rely on zeroed memory.
- 68000 code is GNU as (`m68k-elf-as -m68000 --register-prefix-optional`):
  Motorola register names, but hex is `0x...` (no `$`) and comments start
  with `|`. Hardware addresses are in `rom/a16.inc`; keep it in step with the
  spec. `fetch_build.sh` finds the tools (Homebrew first, since an older
  `m68k-elf-` may be earlier on PATH) or takes the prefix from `$M68K`.
- Boot ROM: `rom/boot.s`, built into `work/arnold16.rom`. It loads a
  program from the serial port (format in `tools/mkload.py`).
- Demo: the 68000 program is `demo/demo.s`. `demo/mkdemo.py` builds its
  tables and a generated `work/demo.inc` (constants shared with Python and
  the tests), and a disc (`work/demo.dsk`, via `tools/mkdsk.py`) holding the
  Z80 side as DISC.BIN at &4000. CPCEC
  boots a 6128 to BASIC and types RUN"DISC itself, so the demo starts about
  160 frames into a run (`START` in `tests/test_demo.py`). The
  Z80 side scans the keyboard and writes the sound chip without the firmware.
- 68000 programs are built by `fetch_build.sh` (`asm68k`, `asm68k_load`) into
  `work/`: the boot ROM, the demo, and the test programs `tests/*.s` that
  `test_video.py` and `test_boot.py` run. In GNU as, `|` is a comment even
  inside an expression: combine bit fields with `+`.
- Z80 code: the small Python assembler `asm/z80.py`.
- Serial input and `--a16-keys` exist for loading programs and for tests.
