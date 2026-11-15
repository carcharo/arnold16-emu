# arnold16-emu: brief for AI sessions

Read `README.md` first. The hardware this emulates is defined in the private
repo `carcharo/arnold16-docs`, file `spec/hardware-spec-v0.2.md`. The spec is
the authority: if the code and the spec disagree, stop and ask which is right.

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
- `fetch_build.sh` wipes `work/src` back to the pinned commit. Regenerate the
  patch before running it.
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
- Boot ROM: `rom/mkboot.py`, built into `work/arnold16.rom`. `rom/m68k.py`
  knows only the instructions the ROM uses; add encodings with care and check
  each against the 68000 manual.
