#!/usr/bin/env python3
"""Wraps a raw 68000 program for the Arnold 16 boot ROM's serial loader.

    python3 tools/mkload.py program.bin 0x1000 program.a16

The loader format is: the four bytes "A16L", the load address (4 bytes, high
byte first), the length (4 bytes), then the program. The boot ROM copies the
program to the load address and jumps to it.
"""
from __future__ import annotations

import struct
import sys

MAGIC = b"A16L"


def wrap(program: bytes, address: int) -> bytes:
    return MAGIC + struct.pack(">II", address, len(program)) + program


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:
        program = f.read()
    with open(sys.argv[3], "wb") as f:
        f.write(wrap(program, int(sys.argv[2], 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
