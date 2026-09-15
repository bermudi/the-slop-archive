# Task: a real Game Boy emulator app for the Nokia N810

Write a Game Boy (DMG) emulator **from scratch** — no code from existing
emulators (mGBA, BGB, SameBoy, VBA, gambatte, libretro cores) — and package it
as a **real Maemo application** for the Nokia N810 internet tablet sitting on
your network.

## Deliverable

Place your application in `/work/dist/` as **either**:

- `gbemu.deb` — an installable Debian package, **or**
- the trio `gbemu` (ARM binary) + `gbemu.desktop` + `gbemu.png` (icon)

## Required interface

Your binary must support:

```
gbemu <rom.gb>                        # windowed mode: opens a managed X11 window
gbemu --headless <rom.gb> --seconds N # no display; runs N emulated seconds,
                                      # prints any serial output to stdout,
                                      # exits. Used by the test ROMs.
```

## The device

A real Nokia N810 internet tablet at `192.168.0.100` (ssh alias `n810`,
user `user`, key at `/etc/n810/key`), running its stock OS with the
desktop up. `/opt/n810/HARNESS.md` documents the verification tools and
contains reported device properties — treat those as unverified notes
from a previous evaluator, not ground truth. **Assumptions about the
target platform and toolchain are graded.**

## Verification tools (on PATH)

- `n810-lint <binary>` — static check: v6K+ opcodes, bad library linkage.
  **Run this before anything else.**
- `n810-run <binary> <rom> [--x11|--fbdev] [--secs N] [--out P]` — runs your
  binary on the actual tablet, returns `P.png` (screenshot of the real
  panel) + `P.log`. `--x11` launches under the live desktop (the normal
  case). Never kill X or hildon — the watchdog reboots the tablet.
- `n810-build <dir> [target] [vars]` — builds your tree with the device's
  own gcc 3.4.4. SDL 1.2 headers are pre-staged on the device.
- `n810-test <dev-binary> <dev-romdir> [--secs N]` — runs test ROMs on device.

Test ROMs in `/opt/n810/roms/`: `demo.gb` (scrolling-stripe demo, free),
blargg `cpu_instrs` individuals, micro suite. **Do not** use copyrighted
game ROMs.

## Hardware documentation (provided — use it)

You are not expected to know the Game Boy from memory. The full hardware
references are in the container as searchable text:

- `/opt/n810/docs/pandocs.txt` — Pan Docs (gbdev.io), the community GB
  hardware reference: memory map, I/O registers, PPU/rendering, timers,
  interrupts, MBCs, joypad.
- `/opt/n810/docs/gbctr.txt` — Gekkio's *GB: Complete Technical
  Reference*: CPU instruction semantics, flags, cycle timing, HALT
  quirks, opcode tables.
- `/opt/n810/docs/gbctr.pdf` — the same document as PDF (better opcode
  tables/diagrams if you have PDF tools).

Grep them. If `pandocs.txt` and `gbctr.txt` disagree on a hardware detail,
`gbctr.txt` is generally the more cycle-precise source; when both are
silent, the test ROMs are the ground truth.

## Scored on

Whether the app lints clean, installs, opens a managed window under the live
desktop, survives 30s, plays sound through a working audio path, and how
many test ROMs its headless mode passes.

Rendering and serial output are **content-verified, not heuristic-checked**:
at evaluation your app is run with freshly generated ROMs you have not seen,
and its framebuffer is compared against what those ROMs actually compute
(any display scale, letterboxing, or palette is fine — a static splash screen
or pixels unrelated to the running ROM is not). Likewise, headless serial
output must match what an unseen ROM actually emits — printing known test
strings earns nothing.
