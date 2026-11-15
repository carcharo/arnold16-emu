| Test ROM for tests/test_video.py: sets up one picture for the video chip.
| GNU as; built by fetch_build.sh into work/test-video.rom, used in place of
| the boot ROM (--a16-rom). test_video.py describes the picture and checks it.
|
| Branches are written .w and absolute addresses (...).l, as the earlier
| Python-built ROM had them, so this one is byte-identical to it.

        .include "a16.inc"

        .macro  colour index, rgb               | set palette entry \index to 0RGB \rgb
        move.w  #\rgb,(PALETTE+\index*2).l
        .endm

        .macro  sprite n, x, y, pattern, flags  | fill in sprite table entry \n
        move.w  #\x,(SPRITES+\n*8).l
        move.w  #\y,(SPRITES+\n*8+2).l
        move.w  #(\pattern<<8)+\flags,(SPRITES+\n*8+4).l
        .endm

        .text
        .globl  start
        dc.l    RAM_TOP                         | reset: initial stack pointer
        dc.l    start                           | reset: start address

| bitmap: 128 KB, each byte = low 8 bits of its address = its x position & 255
start:  lea     (BITMAP).l,a0
        move.l  #0x20000-1,d1
fill:   move.w  a0,d0
        move.b  d0,(a0)+
        subq.l  #1,d1
        bpl.w   fill
        move.b  #6,(BITMAP+1*512+5).l           | the marker: bitmap (5,1) = colour 6

| sprite patterns: 2 = all colour 7 with a transparent first pixel per row,
| 3 = all colour 4
        lea     (PATTERNS+2*256).l,a0
        moveq   #15,d1
pattern2_row:
        clr.b   (a0)+
        moveq   #14,d0
pattern2_pixel:
        move.b  #7,(a0)+
        dbra    d0,pattern2_pixel
        dbra    d1,pattern2_row
        move.w  #255,d0                         | pattern 3 follows pattern 2
pattern3:
        move.b  #4,(a0)+
        dbra    d0,pattern3

| palette entries used by the test (COLOURS in test_video.py): index, 0RGB
        .irp    entry,"0,0x888","1,0xFFF","3,0xF00","4,0x00F","5,0x0F0","6,0xFF0","7,0x0FF"
        colour  \entry
        .endr

| sprites
        sprite  0, 100, 50, 2, 1                | visible
        sprite  1, 200, 50, 2, 3                | visible, flipped left to right
        sprite  5, 108, 50, 3, 1                | overlaps sprite 0 by 8 pixels
        sprite  6, -8, 100, 3, 1                | half off the left edge

        move.w  #509,(SCROLL_X).l
        move.w  #254,(SCROLL_Y).l
        move.w  #100,(RASTER_LINE).l
        move.l  #raster,(VEC_RASTER).l
        move.l  #frame,(VEC_FRAME).l
        move.w  #0x000F,(VID_CTRL).l            | display, sprites, frame and raster interrupts
idle:   stop    #0x2000
        bra.w   idle

frame:                                          | level 6: the picture has ended
        move.w  #2,(VID_STAT).l                 | write 1 to bit 1: drops the frame interrupt only
        move.w  #5,(BORDER).l                   | green
        rte

raster:                                         | level 4: line 100 starts
        move.w  #4,(VID_STAT).l                 | write 1 to bit 2: drops the raster interrupt only
        move.w  #1,(BORDER).l                   | white
        rte

        .org    ROM_SIZE, 0xFF                  | fill the rest of the 64 KB with $FF
