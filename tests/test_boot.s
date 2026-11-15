| Test program for tests/test_boot.py, loaded through the boot ROM's serial
| loader. GNU as; built by fetch_build.sh, linked at LOAD (0x1000) and wrapped
| into work/test-boot.a16. It reports on the serial port:
|
|   M000    RAM and video RAM are zero in each of the three ranges below
|           (a ! in place of a 0 means that range was not cleared)
|   S7751   VID_STAT's low byte after frame and raster fire on the same line,
|           again after a second read, after writing 2, and after writing 4
|
| Branches are written .w and absolute addresses (...).l, as the earlier
| Python-built program had them, so this one is byte-identical to it.

        .include "a16.inc"

        .macro  report char                     | send one character on the serial port
        move.b  #\char,(SER_DATA).l
        .endm

        .macro  report_vstat                    | VID_STAT's low byte, as one digit 0-7
        move.b  (VID_STAT+1).l,d0
        addi.b  #'0',d0
        move.b  d0,(SER_DATA).l
        .endm

        .macro  check_zero n, from, to          | OR every long word of from-to together
        lea     (\from).l,a0
        move.l  #(\to-\from)/4,d1
        moveq   #0,d2
or_\n:  or.l    (a0)+,d2
        subq.l  #1,d1
        bne.w   or_\n
        tst.l   d2
        beq.w   zero_\n
        report  '!'                             | this range was not cleared
        bra.w   next_\n
zero_\n:
        report  '0'
next_\n:
        .endm

        .text
        .globl  start

| 1. memory. The program sits at 0x1000-0x1FFF, the stack at the top of RAM.
start:  report  'M'
        check_zero 0, 0x000400, 0x001000        | RAM above the vectors, below the program
        check_zero 1, 0x002000, 0x0FF000        | RAM above the program, below the stack
        check_zero 2, VRAM, VRAM+VRAM_SIZE      | all of video RAM
        report  '\n'

| 2. VID_STAT: frame and raster on the same line
        move.w  #200,(RASTER_LINE).l
        move.w  #6,(VID_STAT).l                 | start from a clean state
wait:   btst    #1,(VID_STAT+1).l               | until the frame event has happened
        beq.w   wait
        report  'S'
        report_vstat                            | 7: vblank, frame, raster
        report_vstat                            | 7 again: the read cleared nothing
        move.w  #2,(VID_STAT).l                 | clear the frame bit only
        report_vstat                            | 5: raster still pending
        move.w  #4,(VID_STAT).l                 | clear the raster bit
        report_vstat                            | 1: only vblank left
        report  '\n'

idle:   bra.w   idle
