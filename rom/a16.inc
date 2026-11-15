| Arnold 16 hardware addresses for 68000 code, from the hardware spec v0.3
| (arnold16-docs, spec/hardware-spec-v0.3.md). GNU as syntax: hex is 0x...,
| comments start with |.   .include "a16.inc"

| --- memory map --------------------------------------------------------------
        .equ    RAM_TOP,        0x100000        | 1 MB of RAM ends here; the boot ROM's stack starts here
        .equ    VRAM,           0xE00000        | video RAM, 256 KB
        .equ    VRAM_SIZE,      0x40000
        .equ    BITMAP,         0xE00000        | 512 x 256, one byte per pixel
        .equ    PATTERNS,       0xE20000        | 64 sprite patterns of 256 bytes
        .equ    ROM,            0xF00000        | boot ROM, 64 KB
        .equ    ROM_SIZE,       0x10000

| --- 68000 vectors -----------------------------------------------------------
        .equ    VECTORS_END,    0x400           | end of the exception vector table
        .equ    VEC_MAILBOX,    0x68            | level 2 autovector
        .equ    VEC_RASTER,     0x70            | level 4 autovector
        .equ    VEC_FRAME,      0x78            | level 6 autovector

| --- video registers (words) ---------------------------------------------------
        .equ    VID_CTRL,       0xFF0000        | bit 0 display, 1 sprites, 2 frame irq, 3 raster irq
        .equ    VID_STAT,       0xFF0002        | bit 0 vblank, 1 frame, 2 raster; write 1 to clear 1 or 2
        .equ    SCROLL_X,       0xFF0004
        .equ    SCROLL_Y,       0xFF0006
        .equ    RASTER_LINE,    0xFF0008
        .equ    VCOUNT,         0xFF000A
        .equ    BORDER,         0xFF000C
        .equ    SPRITES,        0xFF0100        | 32 entries of 8 bytes
        .equ    PALETTE,        0xFF0200        | 256 words, 0RGB

| --- mailbox -----------------------------------------------------------------
        .equ    MBOX_CMD,       0xFF1001        | read takes the Z80's command, write sends one
        .equ    MBOX_STAT,      0xFF1003        | bit 0 message from the Z80, bit 1 ours not yet read
        .equ    MBOX_DATA,      0xFF1004        | four bytes

| --- debug serial port ---------------------------------------------------------
        .equ    SER_DATA,       0xFF2001
        .equ    SER_STAT,       0xFF2003        | bit 0 byte arrived, bit 1 can send

| --- mailbox commands ----------------------------------------------------------
        .equ    CMD_KEY,        0x01
        .equ    CMD_AY_WRITE,   0x02
        .equ    CMD_EXIT,       0x03
        .equ    CMD_PING,       0x7F
