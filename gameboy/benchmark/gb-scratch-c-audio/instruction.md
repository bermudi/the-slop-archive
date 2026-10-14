# Task: a Game Boy emulator from scratch, in C — with audio

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
gbemu <rom.gb>                                              # opens an SDL2 window, plays the ROM
                                                            # with sound via SDL audio
gbemu --headless <rom.gb> --seconds N                       # no window: runs N emulated
                                                            # seconds, prints any serial output
                                                            # to stdout, exits 0
gbemu --headless <rom.gb> --seconds N --frame-out out.ppm   # as above, plus writes the final
                                                            # LCD frame as a binary PPM (P6),
                                                            # exactly 160x144
gbemu --headless <rom.gb> --seconds N --wav-out out.wav     # as above, plus writes the
                                                            # captured audio as a PCM WAV file,
                                                            # 44100 Hz (mono or stereo)
```

Windowed mode is a real SDL2 window — scale up the 160x144 LCD and run at
roughly realtime, with audible output through SDL audio. Joypad input is a
nice-to-have; it is not scored.

The Game Boy APU has four channels — two pulse (with sweep/envelope), a
wavetable channel, and a noise channel — driven by a 512 Hz frame
sequencer, plus the channel mixer/panner registers `FF24`–`FF26` and the
`FF10`–`FF23` voice registers. Pan Docs' *Audio* section covers all of it.
`dmg_sound` under `/opt/gb/roms/` is blargg's APU test suite; note it
prints its verdict on the **LCD**, not over serial — use `--frame-out` or
a window to see it.

## Provided in this container

- `/opt/gb/roms/` — test ROMs: `demo.gb` (scrolling demo), blargg's
  `cpu_instrs` individuals (`01-special` through `11-op a,(hl)`), the micro
  serial suite (`alu.gb`, `hello.gb`, `intr.gb`, `jr.gb`, `trap.gb`), and
  `dmg_sound/` (blargg's APU suite: registers, length counters, trigger,
  sweep, wave RAM behavior). The cpu_instrs/micro pass/fail signal is
  printed on the Game Boy's serial port (SB=`FF01`, SC=`FF02`) — your
  `--headless` mode must forward serial bytes to stdout. Do not use
  copyrighted game ROMs.
- `/opt/gb/docs/` — the hardware references:
  - `pandocs.txt` — Pan Docs (gbdev.io): memory map, I/O registers,
    PPU/rendering, timers, interrupts, MBCs, joypad, APU.
  - `gbctr.txt` — Gekkio's *GB: Complete Technical Reference*: exact CPU
    instruction semantics, flags, cycle timing, HALT quirks, opcode tables.
  - `gbctr.pdf` — the same document as PDF (better opcode tables if you
    have PDF tools).

You are not expected to know the Game Boy from memory — grep the docs.
When docs disagree or are silent, the test ROMs are the ground truth.

## Scored on

Whether `/work/dist/gbemu` is a real emulator: what fraction of the test
suite it passes in headless mode, whether it opens and sustains an SDL2
window, whether its rendered frame is correct — and whether its APU is
correct: audio captured via `--wav-out` is spectrally compared against a
freshly generated tone-sequence ROM, and a subset of `dmg_sound` is scored
by rendered output.

Rendering, serial output, and audio are **content-verified, not
heuristic-checked**: at evaluation your binary is run on freshly generated
ROMs you have not seen, and its framebuffer, serial output, and audio are
compared against what those ROMs actually compute and play. Printing known
test strings, drawing a canned frame, or emitting a canned WAV earns
nothing.

The network is restricted — everything you need is already in the
container.
