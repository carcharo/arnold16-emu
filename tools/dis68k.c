/* dis68k: disassemble a raw 68000 binary with Musashi's disassembler.
 * Used by tests/test_asm.py to check the Python assembler in rom/m68k.py.
 *
 *   dis68k FILE ORG      ORG is the address of the first byte, in hex
 *
 * Prints one line per instruction: address, then the instruction text.
 * GPL-3.0 like the rest of this repo; Musashi itself is MIT.
 */
#include <stdio.h>
#include <stdlib.h>
#include "m68k.h"

static unsigned char mem[1 << 16];
static unsigned int org, size;

static unsigned int byte_at(unsigned int a)
{
	return a >= org && a < org + size ? mem[a - org] : 0;
}
unsigned int m68k_read_disassembler_8(unsigned int a) { return byte_at(a); }
unsigned int m68k_read_disassembler_16(unsigned int a) { return (byte_at(a) << 8) | byte_at(a + 1); }
unsigned int m68k_read_disassembler_32(unsigned int a)
{
	return (m68k_read_disassembler_16(a) << 16) | m68k_read_disassembler_16(a + 2);
}

int main(int argc, char **argv)
{
	char text[256];
	unsigned int pc;
	FILE *f;
	if (argc != 3 || !(f = fopen(argv[1], "rb")))
		return fprintf(stderr, "usage: dis68k FILE ORG\n"), 2;
	size = fread(mem, 1, sizeof(mem), f);
	fclose(f);
	org = strtoul(argv[2], NULL, 16);
	for (pc = org; pc < org + size;)
	{
		unsigned int n = m68k_disassemble(text, pc, M68K_CPU_TYPE_68000);
		printf("%06X %s\n", pc, text);
		pc += n;
	}
	return 0;
}
