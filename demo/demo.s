| The Arnold 16 proof-of-concept demo: the 68000 side. GNU as; built by
| fetch_build.sh, linked at LOAD (0x1000) and wrapped by tools/mkload.py into
| work/demo.a16 for the boot ROM's serial loader.
|
| It fills the 512 x 256 bitmap with a pattern, scrolls it one pixel per
| frame, moves three sprites across it, and lets the cursor keys steer a
| fourth. SPACE plays a short beep. ESC ends the demo: it sends EXIT, and the
| Z80 side (in demo/mkdemo.py) puts the 68000 back into reset.
|
| demo/mkdemo.py makes the files included here, in work/:
|   demo.inc            constants shared with Python and the tests
|   demo-palette.bin    256 palette words
|   demo-patterns.bin   sprite patterns 0 (ball) and 1 (diamond)
|
| Branches are written .w and absolute addresses (...).l, as the earlier
| Python-built program had them, so this one is byte-identical to it.

        .include "a16.inc"
        .include "demo.inc"

| CPC key numbers
        .equ    KEY_UP, 0
        .equ    KEY_RIGHT, 1
        .equ    KEY_DOWN, 2
        .equ    KEY_LEFT, 8
        .equ    KEY_SPACE, 47
        .equ    KEY_ESC, 66

| variables, in RAM below the program
        .equ    V_TICK, 0x800                   | set by the frame interrupt
        .equ    V_EXIT, 0x801                   | ESC was pressed
        .equ    V_BEEP, 0x802                   | SPACE was pressed
        .equ    V_BEEP_TIMER, 0x803             | frames until the beep stops
        .equ    V_KEY_UP, 0x804                 | 1 while the key is held
        .equ    V_KEY_RIGHT, 0x805
        .equ    V_KEY_DOWN, 0x806
        .equ    V_KEY_LEFT, 0x807
        .equ    V_SCROLL, 0x808                 | word
        .equ    V_PLAYER_X, 0x80A               | word
        .equ    V_PLAYER_Y, 0x80C               | word
        .equ    V_DRIFT, 0x810                  | three words: where sprites 1 to 3 are, 0-511

        .text
        .globl  start
start:  move.w  #0x2700,sr                      | no interrupts while setting up

| variables
        lea     (V_TICK).l,a0
        moveq   #15,d0
clear_vars:
        clr.w   (a0)+
        dbra    d0,clear_vars
        move.w  #PLAYER_X0,(V_PLAYER_X).l
        move.w  #PLAYER_Y0,(V_PLAYER_Y).l
        move.w  #0,(V_DRIFT).l
        move.w  #170,(V_DRIFT+2).l
        move.w  #340,(V_DRIFT+4).l

| palette and sprite patterns, copied from the tables at the end
        lea     palette(pc),a0
        lea     (PALETTE).l,a1
        move.w  #255,d0
copy_palette:
        move.w  (a0)+,(a1)+
        dbra    d0,copy_palette
        lea     patterns(pc),a0
        lea     (PATTERNS).l,a1
        move.w  #511,d0
copy_patterns:
        move.b  (a0)+,(a1)+
        dbra    d0,copy_patterns

| bitmap: each pixel is x XOR y, a pattern that looks the same wherever it wraps
        lea     (BITMAP).l,a1
        moveq   #0,d3                           | y
fill_row:
        moveq   #0,d2                           | x
fill_pixel:
        move.b  d2,d0
        eor.b   d3,d0
        move.b  d0,(a1)+
        addq.w  #1,d2
        cmpi.w  #512,d2
        bne.w   fill_pixel
        addq.w  #1,d3
        cmpi.w  #256,d3
        bne.w   fill_row

| sprites: 0 is the player (pattern 0), 1 to 3 drift across (pattern 1)
        move.w  #0x0001,(SPRITES+4).l           | pattern 0, visible
        move.w  #30,(SPRITES+1*8+2).l
        move.w  #0x0101,(SPRITES+1*8+4).l       | pattern 1, visible
        move.w  #100,(SPRITES+2*8+2).l
        move.w  #0x0101,(SPRITES+2*8+4).l
        move.w  #160,(SPRITES+3*8+2).l
        move.w  #0x0101,(SPRITES+3*8+4).l

        move.w  #NAVY,(BORDER).l
        move.l  #mailbox,(VEC_MAILBOX).l
        move.l  #frame,(VEC_FRAME).l
        move.w  #0x0007,(VID_CTRL).l            | display, sprites, frame interrupt

| --- main loop: sleep until the frame interrupt, then move everything ----------
main:   stop    #0x2000
        tst.b   (V_TICK).l
        beq.w   main
        clr.b   (V_TICK).l

        tst.b   (V_EXIT).l                      | ESC was pressed: hand back to the CPC
        beq.w   no_exit
        moveq   #CMD_EXIT,d0
        moveq   #0,d1
        bsr.w   send
halt:   stop    #0x2700                         | the Z80 will put us in reset
        bra.w   halt
no_exit:

| scroll one pixel down and to the right per frame
        addq.w  #1,(V_SCROLL).l
        move.w  (V_SCROLL).l,d0
        andi.w  #511,d0
        move.w  d0,(SCROLL_X).l
        andi.w  #255,d0
        move.w  d0,(SCROLL_Y).l

| the player's sprite follows the cursor keys and stays on screen
        tst.b   (V_KEY_LEFT).l
        beq.w   not_left
        subi.w  #PLAYER_STEP,(V_PLAYER_X).l
        bpl.w   not_left
        clr.w   (V_PLAYER_X).l
not_left:
        tst.b   (V_KEY_RIGHT).l
        beq.w   not_right
        addi.w  #PLAYER_STEP,(V_PLAYER_X).l
        cmpi.w  #304,(V_PLAYER_X).l
        bls.w   not_right
        move.w  #304,(V_PLAYER_X).l
not_right:
        tst.b   (V_KEY_UP).l
        beq.w   not_up
        subi.w  #PLAYER_STEP,(V_PLAYER_Y).l
        bpl.w   not_up
        clr.w   (V_PLAYER_Y).l
not_up:
        tst.b   (V_KEY_DOWN).l
        beq.w   not_down
        addi.w  #PLAYER_STEP,(V_PLAYER_Y).l
        cmpi.w  #184,(V_PLAYER_Y).l
        bls.w   not_down
        move.w  #184,(V_PLAYER_Y).l
not_down:
        move.w  (V_PLAYER_X).l,(SPRITES).l
        move.w  (V_PLAYER_Y).l,(SPRITES+2).l

| sprites 1 to 3 drift right at different speeds and come round again
        .irp    n,1,2,3
        move.w  (V_DRIFT+(\n-1)*2).l,d0
        addq.w  #\n,d0                          | speed: n pixels per frame
        andi.w  #511,d0
        move.w  d0,(V_DRIFT+(\n-1)*2).l
        subi.w  #96,d0                          | 0-511 becomes -96 to 415
        move.w  d0,(SPRITES+\n*8).l
        .endr

| sound: SPACE starts a beep, which is switched off some frames later.
| AY_WRITE data: byte 0 the register, byte 1 the value.
        tst.b   (V_BEEP).l
        beq.w   no_beep
        clr.b   (V_BEEP).l
        .irp    rv,0x00FE0000,0x01000000,0x073E0000,0x080F0000
        move.l  #\rv,d1                         | tone, tone, mixer, volume 15
        moveq   #CMD_AY_WRITE,d0
        bsr.w   send
        .endr
        move.b  #BEEP_FRAMES,(V_BEEP_TIMER).l
no_beep:
        tst.b   (V_BEEP_TIMER).l
        beq.w   main
        subq.b  #1,(V_BEEP_TIMER).l
        bne.w   main
        move.l  #0x08000000,d1                  | volume of channel A to 0
        moveq   #CMD_AY_WRITE,d0
        bsr.w   send
        bra.w   main

send:                                           | send command d0 with data d1 to the Z80
        btst    #1,(MBOX_STAT).l                | wait until it has taken the last message
        bne.w   send
        move.l  d1,(MBOX_DATA).l
        move.b  d0,(MBOX_CMD).l
        rts

| --- interrupts ----------------------------------------------------------------
frame:                                          | level 6: the picture has ended
        move.w  #2,(VID_STAT).l                 | write 1 to bit 1: drops the frame interrupt
        move.b  #1,(V_TICK).l
        rte

mailbox:                                        | level 2: a message from the Z80
        move.l  d0,-(sp)
        move.l  d1,-(sp)
        move.l  (MBOX_DATA).l,d1
        move.b  (MBOX_CMD).l,d0
        cmpi.b  #CMD_KEY,d0
        bne.w   mailbox_done
        swap    d1                              | low word is now: key number, then 1 = down
        move.w  d1,d0
        lsr.w   #8,d0                           | d0 = key number
        andi.w  #1,d1                           | d1 = 1 if down
        .irp    key,UP,RIGHT,DOWN,LEFT          | the cursor keys: remember up or down
        cmpi.b  #KEY_\key,d0
        bne.w   not_key_\key
        move.b  d1,(V_KEY_\key).l
        bra.w   mailbox_done
not_key_\key:
        .endr
        tst.b   d1                              | the rest act only when pressed
        beq.w   mailbox_done
        cmpi.b  #KEY_SPACE,d0
        bne.w   not_space
        move.b  #1,(V_BEEP).l
not_space:
        cmpi.b  #KEY_ESC,d0
        bne.w   mailbox_done
        move.b  #1,(V_EXIT).l
mailbox_done:
        move.l  (sp)+,d1
        move.l  (sp)+,d0
        rte

| --- tables ----------------------------------------------------------------------
palette:
        .incbin "demo-palette.bin"
patterns:
        .incbin "demo-patterns.bin"
