# Task: a Game Boy emulator from scratch, in C

Write a Game Boy (DMG — the original monochrome Game Boy, not CGB) emulator
**from scratch, in C**, for modern x86-64 Linux. No code from existing
emulators (mGBA, BGB, SameBoy, gambatte, VBA, libretro cores, …) — the
hardware documentation and the test ROMs below are all you get, and they are
sufficient.

The toolchain is modern: current gcc/clang, make or CMake or meson, SDL2.
Use whatever you like.

## Deliverable

- Your source tree anywhere under `/work/`
- A built binary at `/work/dist/gbemu` — a native x86-64 ELF executable

## Required interface

```
gbemu <rom.gb>                                              # opens an SDL2 window and plays the ROM
gbemu --headless <rom.gb> --seconds N                       # no window: runs N emulated
                                                            # seconds, prints any serial output
                                                            # to stdout, exits 0
gbemu --headless <rom.gb> --seconds N --frame-out out.ppm   # as above, plus writes the final
                                                            # LCD frame as a binary PPM (P6),
                                                            # exactly 160x144
```

Windowed mode is a real SDL2 window — scale up the 160x144 LCD and run at
roughly realtime. Joypad input and audio are nice-to-haves; they are not
scored.

## Provided in this container

- `/opt/gb/roms/` — test ROMs: `demo.gb` (scrolling demo), blargg's
  `cpu_instrs` individuals (`01-special` through `11-op a,(hl)`), and the
  micro serial suite (`alu.gb`, `hello.gb`, `intr.gb`, `jr.gb`,
  `trap.gb`). The pass/fail signal is printed on the Game Boy's serial port
  (SB=`FF01`, SC=`FF02`) — your `--headless` mode must forward serial bytes
  to stdout. Do not use copyrighted game ROMs.
- `/opt/gb/docs/` — the hardware references:
  - `pandocs.txt` — Pan Docs (gbdev.io): memory map, I/O registers,
    PPU/rendering, timers, interrupts, MBCs, joypad.
  - `gbctr.txt` — Gekkio's *GB: Complete Technical Reference*: exact CPU
    instruction semantics, flags, cycle timing, HALT quirks, opcode tables.
  - `gbctr.pdf` — the same document as PDF (better opcode tables if you
    have PDF tools).

You are not expected to know the Game Boy from memory — grep the docs.
When docs disagree or are silent, the test ROMs are the ground truth.

## Scored on

Whether `/work/dist/gbemu` is a real emulator: what fraction of the test
suite it passes in headless mode, whether it opens and sustains an SDL2
window, and whether its rendered frame is correct.

Rendering and serial output are **content-verified, not heuristic-checked**:
at evaluation your binary is run on freshly generated ROMs you have not
seen, and its framebuffer and serial output are compared against what those
ROMs actually compute. Printing known test strings or drawing a canned
frame earns nothing.

The network is restricted — everything you need is already in the
container.
