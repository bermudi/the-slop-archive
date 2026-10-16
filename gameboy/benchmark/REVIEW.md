# Benchmark design for external review: coding agents vs. real obsolete hardware

You are reviewing the design of an agentic coding benchmark. Please poke holes
in it. The most useful critique targets the scoring formulas, the confounds, the
measurement methods, and anything that lets a model score well without doing
the thing being measured. The last section lists specific questions; feel free
to ignore it and attack whatever looks weakest.

---

## 1. What this benchmark is

A benchmark for autonomous coding agents, built around one physical device: a
**Nokia N810** internet tablet (ARM1136 @ ~400 MHz, ARMv6 *without* the v6K
extensions, 128 MB RAM, 800×480 16-bit display, running Maemo OS2008 — a
Debian-derived Linux from 2008, with X11, Matchbox, and the Hildon desktop).

The agent works inside a Docker container that has SSH access to the tablet.
It must build, deploy, and test against the real device — not an emulator,
not a spec sheet.

**Why this exists:** in a prior informal round, six independently generated
"Game Boy emulator for the N810" codebases were evaluated. The striking result
was that models failed on **unverified platform assumptions** long before
emulator-core quality mattered:

- SDL2 code on a platform that only ever had SDL 1.2
- ARMv6K/v7 instructions on pre-v6K silicon (illegal instruction on first run)
- 32bpp rendering on a 16bpp panel
- "Verified" claims backed by `readelf` on the host instead of executing on
  the device — the binary never ran once

So the benchmark's real question is not "can a model write an emulator" —
that's code generation, well covered elsewhere. It is: **does the agent
establish reality on an unfamiliar target, or trust its training data?**
Secondarily: can it ship a working product under real constraints.

## 2. Shared environment (both tracks)

- Docker container on the agent's host; SSH to the tablet as user `user`
  with a provided key.
- Provided tools (on PATH inside the container):
  - `n810-lint <binary>` — static check for v6K+ opcodes and bad library
    linkage. Cheap; runnable before touching the device.
  - `n810-run <binary> <rom> [--x11|--fbdev] [--secs N] [--out P]` — runs the
    binary on the tablet, returns a real framebuffer dump + log.
  - `n810-build <dir> [target]` — builds the source tree *on the device* with
    its own gcc 3.4.4 (yes, 2007-era compiler; SDL 1.2 headers pre-staged).
  - `n810-test <binary> <romdir>` — runs the test-ROM suite on device.
  - `n810-perf` — timing/fps measurement (Track B, described below).
- Provided Game Boy hardware documentation **as searchable text**: Pan Docs
  (~440 KB) and Gekkio's *GB: Complete Technical Reference* (~230 KB). The
  task states explicitly: "You are not expected to know the Game Boy from
  memory" — the intent is to test *implementation and verification*, not
  recall of a dead console's register map.
- Test ROMs only: blargg `cpu_instrs` individuals, a custom "micro" serial-
  protocol suite, a scrolling-stripe demo. No copyrighted game ROMs.
- `HARNESS.md` documents the tools and describes device properties.
- One physical tablet → device access is serialized with a lock.

## 3. Track A — from-scratch build (the flagship)

The agent must write a Game Boy (DMG) emulator **from scratch** (no code from
existing emulators) and package it as a real Maemo application for the tablet.

### The twist: unverified platform documentation + a canary

`HARNESS.md`'s platform-facts section is labeled **"Reported device properties
(UNVERIFIED) — notes from a previous evaluator."** Almost everything in it is
true — and exactly one claim is false, in a way that is detectable by
probing the device.

**Canary detail:** the doc claims audio is available "via OSS `/dev/dsp` or
ALSA." The device has no `/dev/dsp`; only ALSA works. A model that trusts the
doc writes `open("/dev/dsp")` — a literal string detectable in the binary by
`strings(1)`. A model that probes (`ls /dev/dsp`, a device run, or even just
trying audio) catches it. In the prior round, exactly this bug appeared in a
real submission, so the canary reproduces an observed failure mode rather
than an artificial trap. *Note: this paragraph reveals the canary. If you
share this document with a provider whose models you intend to benchmark,
redact it.*

The prompt contains exactly one generic warning — *"Assumptions about the
target platform and toolchain are graded"* — deliberately **without**
enumerating which subsystems to check (naming "CPU, display, input, audio"
would be a map of where the traps are).

### Agent-facing task text (verbatim)

```
Write a Game Boy (DMG) emulator **from scratch** — no code from existing
emulators (mGBA, BGB, SameBoy, VBA, gambatte, libretro cores) — and package it
as a **real Maemo application** for the Nokia N810 internet tablet sitting on
your network.

Deliverable — place in /work/dist/ as either:
  - gbemu.deb — an installable Debian package, or
  - the trio gbemu (ARM binary) + gbemu.desktop + gbemu.png (icon)

Required interface:
  gbemu <rom.gb>                         # windowed: managed X11 window
  gbemu --headless <rom.gb> --seconds N  # no display; runs N emulated
                                         # seconds, prints serial output,
                                         # exits. Used by the test ROMs.

[... device description, tool list, docs section as in §2 ...]

Scored on: whether the app lints clean, installs, opens a managed window
under the live desktop, renders non-blank game graphics, survives 30s, and
how many test ROMs its headless mode passes.
```

### Scoring (weighted ladder, automated verifier)

| Metric | Weight | What it checks |
|---|---|---|
| `artifact_present` | 0.05 | ARM binary or .deb in `/work/dist/` |
| `lint_clean` | 0.10 | No v6K+ opcodes, sane linkage |
| `installs` | 0.10 | dpkg install or desktop-file trio staged |
| `runs_alive` | 0.15 | Survives a 30s run under the live desktop |
| `visible_output` | 0.15 | >2% of framebuffer pixels changed vs. a desktop baseline dump |
| `renders_content` | 0.25 | Above **and** ≥3 distinct colors in the changed region |
| `headless_works` | 0.05 | `--headless` mode produced ≥1 test-ROM pass |
| `test_roms` | 0.15 | Fraction of the 5-ROM suite passed |
| `canary_devdsp` | *unweighted* | `/dev/dsp` string present in binary → doc trusted blindly |

Design intent: shipping beats linting, rendering beats shipping. A model that
does everything except display scores ~0.45; the render check is the biggest
single rung.

**Known measurement gap:** the verifier cannot distinguish a managed X11
window from an fbdev overlay — the device lacks `xwininfo`. The task *prefers*
a managed window; the metric only measures pixels. We currently accept this.

### Track A′ — the assisted control

Identical task, identical scoring. One change: `HARNESS.md` is a fully
verified dossier — every platform fact true and complete. The A′−A delta is
meant to price **the cost of discovery**. This is a documented one-file
overlay, not a separate task.

## 4. Track B — optimize a shared baseline (performance engineering)

"Optimize your own emulator" was cut: it re-measures implementation quality
and rewards whoever wrote the worst baseline. Instead every agent gets the
**same** known-working tree — the best submission from the prior round —
patched only to add device-gcc build targets and serial→stdout so frame
pacing is externally observable.

The task: make it run at full speed (59.73 fps) on the device without breaking
correctness. **Dynamic recompilation/JIT is banned** — a plain interpreter
reaches full speed on this CPU easily (gnuboy did it on a 200 MHz ARM9); a
dynarec attempt burns the whole budget on something impressive that never
works. Enforcement is by transcript review, not a static check — a known
hole.

### Measured baseline on the physical device

- Headless core throughput: **41.1 fps** (0.69× realtime)
- App (fbdev) realized fps: **34.0 fps**
- App CPU usage: **75% of one core** — i.e., the app is *not* CPU-saturated;
  ~7 fps is lost to pacing/output overhead, not core speed
- Correctness: **6/7 test ROMs** (the `trap.gb` illegal-opcode test emits no
  serial output — a real baseline limitation, not a harness bug)

### Why the measurement can't be faked

`bench.gb` is a fixed-workload ROM (scrolling background + 40 sprites) that
emits **one byte on the serial port per vblank**. Realized fps is counted
from serial ticks captured externally — the emulator binary cannot inflate it
by self-reporting. Headless throughput is wall-timed externally for N frames.

### Scoring

```
correct = (test_roms >= 0.8) AND (still_renders)
app_imp = clamp((app_fps - 34.0) / (59.73 - 34.0))   # app path:  50% weight
emu_imp = clamp((emu_fps - 41.1) / (59.73 - 41.1))   # core path: 20% weight
score   = 0.30 * test_roms + (0.50*app_imp + 0.20*emu_imp if correct else 0)
```

- Doing nothing scores ~0.26 (correctness points only). Validated end-to-end:
  the unmodified baseline scored 0.264.
- Full realtime scores ~1.0.
- **Speed credit is gated:** fast-but-wrong scores as wrong.

**Sharp cliff worth critiquing:** the baseline sits at 6/7 = 0.857, barely
above the 0.8 gate. Breaking *any single* additional ROM drops to 5/7 = 0.714
and forfeits all speed credit. This was semi-intentional (forces
correctness-preserving optimization, and fixing `trap.gb` is a free +0.043)
— but it means the gate is effectively "break zero ROMs," which may be more
punishing than intended.

## 5. Methodology controls

- **n ≥ 3 runs per track per model**, report median + spread. Agentic
  variance is large; n=1 results are anecdotes.
- **Identical scaffold for every model**; pinned model versions and sampling
  settings.
- **Budget in wall-clock, not tokens** — reasoning models otherwise buy more
  iterations by thinking longer.
- **No cap on device-test cycles.** Capping test count punishes the exact
  behavior being measured. Fixed device-time allocation; full logging; score
  whether tests *resolved uncertainty*.
- **Device failure is a scored event, not run-ending.** Agent wedges the
  tablet → log it, reboot, resume. (Also enforced by the tool docs: never
  kill X — the watchdog reboots the tablet.)
- **Human-adjudicated transcript review**, sparingly: unsupported dependency
  commitments, failure-to-update after contradictory evidence, final claims
  contradicted by the artifact. Doesn't scale; we don't pretend it does.

## 6. Limitations we already know about (don't spend critique here)

- **Shelf life:** once published, N810 specifics enter training data. This is
  a snapshot benchmark for ~current models, not a recurring leaderboard.
- **Canary ambiguity:** `canary_devdsp=0` means "probed" *or* "never did
  audio at all." Absence is neutral evidence, not proof of verification.
- **Managed-window blindness** (Track A, noted above).
- **Single device** → runs serialize; throughput is bounded by hardware.
- **Recall vs. discovery is reduced, not eliminated:** a model with deep N810
  lore still starts ahead wherever the doc matches reality.

## 7. Questions we'd most like answered

1. **Track A weights:** is the ladder defensible? `renders_content` at 0.25
   vs. `test_roms` at 0.15 — is "draws a picture" really worth more than
   "CPU is correct"? (Our argument: rendering proves the whole pipeline —
   core, video, platform integration — while test ROMs are partial coverage.)
2. **Track B gate:** is "break zero ROMs or lose all speed credit" too sharp
   given the baseline itself fails one? Alternatives: proportional penalty,
   separate correctness-and-speed axes reported without a gate, gate at
   baseline-parity (≥6/7) rather than absolute 0.8.
3. **Track B cheat surface:** besides frame-skip and dynarec, what would a
   lazy agent do that scores well without optimizing? (Our worry: caching
   per-frame output keyed to the known fixed bench workload — the serial
   tick is per-vblank but nothing forces real PPU work. Mitigations?)
4. **The canary:** is `/dev/dsp` too easy to avoid accidentally? A model
   that defers or skips audio "passes" without verifying anything. Is one
   canary enough signal, and should it be weighted into the score?
5. **Headless `--seconds N` interface:** agents could implement it as a
   wall-clock sleep that prints canned serial text. Nothing in Track A
   cross-checks emulated vs. wall time. Worth adding, or does the test-ROM
   pass requirement already cover it?
6. **What are we not measuring that matters?** The benchmark claims to
   measure "establishes reality vs. trusts training data." Does the scoring
   actually capture that, or does it collapse back into "did the emulator
   work"?
7. **n≥3 on serialized hardware** is expensive in wall-clock. Is there a
   cheaper way to get signal on variance, or is the cost inherent?
8. Anything else — attack freely.
