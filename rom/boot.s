| Arnold 16 boot ROM, version 0.3. GNU as (m68k-elf-as -m68000
| --register-prefix-optional); built into work/arnold16.rom by fetch_build.sh.
|
| What the ROM does:
|   1. clears the exception vectors ($000008 to $0003FF), points the mailbox
|      interrupt (level 2 autovector) at its handler and allows interrupts,
|   2. prints a banner on the debug serial port,
|   3. clears the rest of RAM and all of video RAM, so a program can rely on
|      them starting at zero (RAM holds junk at power-on). This takes about
|      0.55 s; PING is answered meanwhile,
|   4. waits for a program on the serial port, copies it into RAM and jumps to
|      it (the format is in tools/mkload.py).
| While it waits, the mailbox handler takes every message from the Z80. It
| answers PING with the same four data bytes and drops everything else.
| A loaded program starts in supervisor mode with interrupts allowed and takes
| over the mailbox by pointing the level 2 vector at its own handler.
|
| The ROM sits at $F00000. Its first eight bytes are the 68000 reset vectors,
| which the hardware also shows at $000000: initial stack pointer, then start
| address.
|
| Branches are written .w and absolute addresses (...).l throughout: that is
| what the earlier Python-built ROM used, so this one is byte-identical to it.

        .include "a16.inc"
        .equ    LOAD_MAGIC, 0x4131364C          | "A16L"

        .text
        .globl  start
        dc.l    RAM_TOP                         | reset: initial stack pointer
        dc.l    start                           | reset: start address

start:  moveq   #0,d4                           | d4 stays zero while clearing
        lea     (8).l,a3                        | the vectors first ($000000-7 is the ROM)
        move.w  #(VECTORS_END-8)/4-1,d5
clear_vectors:
        move.l  d4,(a3)+
        dbra    d5,clear_vectors
        move.l  #mailbox,(VEC_MAILBOX).l
        move.w  #0x2000,sr                      | supervisor mode, all interrupts allowed
        lea     banner(pc),a0
        bsr.w   puts

| --- clear RAM and video RAM, 32 bytes a time ---------------------------------
| Not in a subroutine: the stack at the top of RAM is cleared too, which is
| safe only while nothing is on it. The mailbox handler saves and restores
| what it uses, so it may run in between.
        lea     (VECTORS_END).l,a3
        move.w  #(RAM_TOP-VECTORS_END)/32-1,d5
clear_ram:
        .rept   8
        move.l  d4,(a3)+
        .endr
        dbra    d5,clear_ram
        lea     (VRAM).l,a3
        move.w  #VRAM_SIZE/32-1,d5
clear_vram:
        .rept   8
        move.l  d4,(a3)+
        .endr
        dbra    d5,clear_vram

| --- serial loader -------------------------------------------------------------
        moveq   #0,d1
find_magic:                                     | shift bytes in until the last four are "A16L"
        bsr.w   getbyte
        lsl.l   #8,d1
        move.b  d0,d1
        cmp.l   #LOAD_MAGIC,d1
        bne.w   find_magic
        bsr.w   getlong                         | load address
        move.l  d1,a1
        move.l  d1,a2
        bsr.w   getlong                         | length
        move.l  d1,d3
        beq.w   run
copy:   bsr.w   getbyte
        move.b  d0,(a1)+
        subq.l  #1,d3
        bne.w   copy
run:    lea     loaded(pc),a0
        bsr.w   puts
        jmp     (a2)

getbyte:                                        | wait for a byte from the serial port, into d0
        btst    #0,(SER_STAT).l
        beq.w   getbyte
        move.b  (SER_DATA).l,d0
        rts

getlong:                                        | four bytes, high byte first, into d1
        moveq   #3,d2
getlong_next:
        bsr.w   getbyte
        lsl.l   #8,d1
        move.b  d0,d1
        dbra    d2,getlong_next
        rts

puts:                                           | print the zero-terminated string at a0
        move.b  (a0)+,d0
        beq.w   puts_done
        move.b  d0,(SER_DATA).l
        bra.w   puts
puts_done:
        rts

| --- mailbox -------------------------------------------------------------------
mailbox:                                        | level 2 interrupt: a message from the Z80
        move.l  d0,-(sp)
        move.l  d1,-(sp)
        move.l  (MBOX_DATA).l,d1                | the data first: reading the command frees the mailbox
        move.b  (MBOX_CMD).l,d0                 | take the command; this also drops the interrupt
        cmp.b   #CMD_PING,d0
        bne.w   mailbox_done
mailbox_wait:                                   | wait until the Z80 has taken our last message
        btst    #1,(MBOX_STAT).l
        bne.w   mailbox_wait
        move.l  d1,(MBOX_DATA).l
        move.b  #CMD_PING,(MBOX_CMD).l
mailbox_done:
        move.l  (sp)+,d1
        move.l  (sp)+,d0
        rte

banner: .asciz  "Arnold 16 boot ROM v0.3\n"
        .even                                   | keep what follows on a word boundary
loaded: .asciz  "Program loaded\n"
        .even

        .org    ROM_SIZE, 0xFF                  | fill the rest of the 64 KB with $FF
