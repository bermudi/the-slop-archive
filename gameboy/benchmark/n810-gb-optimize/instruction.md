# Task: make a Game Boy emulator fast enough on real hardware

`/work/baseline/` contains a working Game Boy (DMG) emulator that renders
correctly on the Nokia N810 — but slowly (~20-30% of realtime). Your job:
**make it run at full speed on the device without breaking correctness.**

## Constraints

- Optimize the existing core — do not replace it with a different emulator
  or port an existing one (no mGBA/SameBoy/gambatte code).
- **No dynamic recompilation / JIT.** A plain interpreter is sufficient on
  this CPU; a dynarec attempt will eat your entire budget.
- Correctness must not regress: the blargg `cpu_instrs` suite and the micro
  ROMs must still pass.
- The required interface must be preserved:
  - `gbn810-arm <rom.gb>` — the fbdev app (platform code in `src/plat_n810.c`)
  - `gbn8-arm-headless <rom.gb> --frames N` — headless build
    (`src/plat_headless.c`) used for measurement and test ROMs

## Building and measuring

- `n810-build /work/baseline arm` / `n810-build /work/baseline arm-headless`
  — builds on the device with its own gcc. Artifacts land in
  `~/bench/baseline/` on the tablet.
- `n810-perf --headless <binary> [--frames N]` — wall-times N emulated
  frames on device. Ground truth for core speed. 59.73 fps = 1.00x.
- `n810-perf --app <binary> [--secs N]` — runs the fbdev app on `bench.gb`
  and reports realized fps from serial ticks plus %CPU of one core.
- `n810-test` — the test-ROM suite (see HARNESS.md).
- `n810-lint` — run before pushing anything.

`bench.gb` (`/opt/n810/roms/bench.gb`) is a fixed-workload ROM: scrolling
background + 40 sprites + one serial byte per vblank. Every tick byte is
derived from a per-run PRNG and from the DIV timer at vblank — scoring
counts only bytes that match the expected stream, so a binary that prints
ticks on a timer without emulating scores zero. Keep serial output on
stdout byte-exact (logs to stderr). The public ROM is the seed-0 dev
variant; scoring runs freshly generated private variants of the same
workload. Use `bench.gb` for all speed measurement so your numbers are
comparable.

## Deliverable

Your optimized tree at `/work/baseline/` (edit in place), AND the built
artifacts staged in `/work/dist/`:

- `gbn810-arm` — the app binary
- `gbn8-arm-headless` — the headless binary

## Scored on

Emulated speed on real hardware (headless throughput + realized app fps +
CPU headroom), gated by correctness — only a build that still passes the
test ROMs earns speed credit.

A real Nokia N810 is at `192.168.0.100` (ssh alias `n810`). Hardware
references live in `/opt/n810/docs/`; `/opt/n810/HARNESS.md` documents the
tools and verified platform facts.
