# gbn810 - Game Boy emulator for the Nokia N810
#
#   make host  - headless test binary for this machine (x86 or whatever)
#   make n810  - static ARM binary for Maemo OS2008 (N810), via zig cc
#   make test  - build + run all hardware test ROMs (fetches them if missing)

CC      ?= cc
ZIG     ?= zig
CFLAGS  ?= -O2 -std=c99 -Wall -Wextra -fno-strict-aliasing

CORE = src/gb.c src/cpu.c src/mmu.c src/ppu.c src/timer.c src/apu.c

all: host n810

host: $(CORE) src/plat_headless.c
	$(CC) $(CFLAGS) -o gbn8 $(CORE) src/plat_headless.c

n810: $(CORE) src/plat_n810.c
	$(ZIG) cc -target arm-linux-musleabi -mcpu=arm1136j_s -static -s \
		-O2 -std=c99 -Wall -Wextra -fno-strict-aliasing \
		-o gbn810 $(CORE) src/plat_n810.c

# device targets — build on the N810 itself (its gcc can't emit instructions
# its own CPU can't run). FBIO_WAITFORVSYNC is missing from the device headers;
# 0x40044620 is the standard OMAP1/DSS value (_IOW('F',0x20,__u32)).
arm: $(CORE) src/plat_n810.c
	$(CC) -O2 -std=gnu99 -Wall -fno-strict-aliasing $(CFLAGS) \
		-DFBIO_WAITFORVSYNC=0x40044620 -o gbn810-arm $(CORE) src/plat_n810.c $(LDFLAGS)

arm-headless: $(CORE) src/plat_headless.c
	$(CC) -O2 -std=gnu99 -Wall -fno-strict-aliasing $(CFLAGS) \
		-o gbn8-arm-headless $(CORE) src/plat_headless.c $(LDFLAGS)

test: host
	./test/run_tests.sh

clean:
	rm -f gbn8 gbn810

.PHONY: all host n810 test clean
