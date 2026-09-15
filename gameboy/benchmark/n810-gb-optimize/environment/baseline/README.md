# gbn810 — a Game Boy emulator for the Nokia N810

A DMG (original Game Boy) emulator written from scratch in C. No emulator
cores, no SDL, no X11 — one static ARM binary that draws to the framebuffer,
reads the hardware buttons and plays audio through OSS.

*Coded by zai/glm-5.3-flash:max.*

```
src/gb.h            core types
src/cpu.c           Sharp LR35902 interpreter (cycle-accurate bus access)
src/ppu.c           scanline renderer (modes 2/3/0, window, sprites)
src/timer.c         DIV/TIMA/TMA/TAC with falling-edge detection
src/apu.c           4-channel sound (pulse x2, wave, noise), integer-only
src/mmu.c           memory map, MBC1/2/3/5 (+RTC), joypad, serial, OAM DMA
src/gb.c            glue: boot state, frame pump
src/plat_n810.c     N810 platform: /dev/fb0, /dev/input/event*, /dev/dsp
src/plat_headless.c headless platform for testing
test/               test ROM harnesses and blargg's hardware test ROMs
```

## Build

- `make host` — headless test binary for any POSIX machine (needs a C compiler)
- `make n810` — static ARM binary for the N810 (needs [zig](https://ziglang.org))
- `make test` — run the test suite (conformance ROM, PPU assertions, blargg ROMs)

## Install on the N810 (OS2008)

Copy `gbn810` and your `.gb` ROM to the device (USB mass storage, `scp`, or an
MMC card), then from an osso-xterm or serial root shell:

```
sudo gainroot
/etc/init.d/xomap stop        # the boot X server owns /dev/fb0
/mmc2/gbn810 /mmc2/tetris.gb  # or wherever you put it
```

Return to normal with `/etc/init.d/xomap start`.

### Controls

| GB      | N810                                          |
|---------|-----------------------------------------------|
| D-pad   | hardware 5-way d-pad / keyboard arrows        |
| A       | `X` or Right Shift                            |
| B       | `Z` or Left Shift                             |
| Start   | Enter                                         |
| Select  | Backspace or Chr                              |
| Quit    | Home bezel key or Esc                         |

- 160x144 scales 3x centered on the 800x480 panel; `GBN8_PALETTE=gray` for the
  classic grayscale look (default is the green DMG palette).
- Battery saves go to `<rom>.sav` next to the ROM.
- Audio uses OSS (`/dev/dsp`); if the device refuses it, the emulator runs
  silent. `--mute` disables audio.

## Accuracy

Verified against blargg's hardware test ROMs (in `test/roms/`):

| suite        | result            |
|--------------|-------------------|
| cpu_instrs   | **11/11 passed**  |
| mem_timing   | read timing ok; write/modify timing pending |
| instr_timing | timer phase detail pending |
| halt_bug     | (screen-output ROM; untested) |

Plus an in-house 29-case CPU conformance ROM (`test/gen_conformance.py`) and
18 exact-pixel PPU assertions (`test/gen_ppu_test.py`) — both fully passing.

Known simplifications: DMG only (no GBC), OAM DMA is instant (no 160-cycle
bus stall), and the timer's sub-instruction phase ordering differs from
silicon by one M-cycle (blargg's timer suites catch this; games do not care).

## Headless use

```
gbn8 <rom.gb> [--frames N] [--ppm FILE]
```

Runs a ROM without a display, prints serial output (test ROMs report over
serial) and optionally dumps a screenshot as PPM.
