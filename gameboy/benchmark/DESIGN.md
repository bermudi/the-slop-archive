# N810 Game Boy benchmark — final design

Synthesis of the ChatGPT thread plus three independent critiques (fable5.1,
astra6, kimi-k3). Where they conflicted, the call is noted.

## What this benchmark actually measures

Not "can a model write an emulator" — that's a code-generation question with
hundreds of existing benchmarks. The distinctive thing our round one proved:
**models fail on unverified platform assumptions before the emulator core ever
matters** (SDL2 on a platform that never had it, v6K opcodes on pre-K silicon,
32bpp on a 16bpp panel, "verified" via readelf instead of execution).

So the benchmark measures: **does the agent establish reality, or trust its
training data?** — and secondarily, whether it can ship a real product.

## Experiment structure

Four tracks, not two. The A/B pair died the moment B became a different task;
each piece is now its own experiment with a clean question.

### Track A — flagship: autonomous engineering (existing task, modified)

The current `n810-gb-emulator` task, with these changes:

- Agent gets: task instruction, pandocs.txt + gbctr.txt (Game Boy hardware
  truth — we are testing *implementation*, not *recall*), the n810-* harness
  tools, device SSH access.
- `HARNESS.md` documents **tool usage** (what n810-run does, flags, outputs)
  but its platform-facts section is replaced with **unverified claims** — and
  exactly one of them is wrong (the canary, below).
- The prompt contains one generic line: *"Assumptions about the target
  platform and toolchain are graded."* **No enumerated subsystem list** — naming
  "CPU, display, input, audio" is a map of where the traps are (fable5.1).

**The canary (kimi-k3's contribution, adopted):** one claim in HARNESS.md
deviates from the hardware in a way that is detectable by probing. Chosen:
*"audio via OSS `/dev/dsp` or ALSA `default`"* — `/dev/dsp` doesn't exist;
only ALSA/esd do. A model that trusts the doc re-creates gbemu_n810's exact
failure; one that probes (`ls /dev/dsp`, a device run) catches it. This
converts "did it know N810 trivia" into "does it verify" — and makes
memorized platform lore a *liability*, which is the point.

**Implementation status (done):**
- `environment/tools/HARNESS.md` is the Track A variant: tool docs +
  "Reported device properties (UNVERIFIED)" containing true facts and the
  `/dev/dsp` canary. The host `tools/HARNESS.md` remains the verified
  dossier.
- `instruction.md` no longer enumerates platform facts; one generic line:
  "Assumptions about the target platform and toolchain are graded."
- `tests/test.sh` reports `canary_devdsp` — 1 if the submitted binary/deb
  embeds the string `/dev/dsp` (doc trusted blindly), 0 otherwise.
  Reported, not weighted into the score.
- **Track A′ overlay:** to run the assisted control, copy the host
  `tools/HARNESS.md` (verified dossier) over `environment/tools/HARNESS.md`
  before building the image. Everything else is identical.

**Verifier hardening (post-review, done): content-verified rendering.**
The original checks (">2% pixels changed, ≥3 colors") were satisfied by any
window — an app that draws three rectangles and sleeps scored 0.80 with zero
emulation, and a `printf("Passed")` stub took the remaining 0.20. Now:

- **Challenge ROM** (`tests/mkchallenge.py`): generated fresh per run from a
  random seed. Its tiles and tilemap do not exist in the ROM image — the
  ROM's CPU computes them at runtime (LCG with seed-dependent increment;
  the picture is a function of ~30 opcodes actually executing). 256
  distinct screens per seed space; adjacent seeds differ on ~72% of pixels.
  Two lessons baked in from validation: seed must enter via the LCG
  *increment* (initial-state seeding yields one universal sequence rotated
  across seeds), and the serial signature must be raw stream bytes (every
  byte this ROM computes is affine in the seed mod 256, so any additive or
  XOR checksum over it proved seed-independent — empirically constant).
- **Reference oracle + instrument guard** (`tests/ref/`, vendored gb4n810
  core): the verifier builds the trusted emulator and renders the golden
  frame; the generator's independent Python model must agree byte-for-byte
  (frame AND serial) or the verifier exits 4 and refuses to score.
- **Matcher** (`tests/render_check.py`): correlation of the framebuffer
  against the golden at scales 1–3×, arbitrary offsets, stretch-to-window,
  and letterbox insets; palette-agnostic (inverted BGP accepted). Plus a
  temporal check: two dumps of one demo.gb run must differ inside the app's
  window (demo.gb scrolls; static frames fail). `selftest` is the adversarial
  suite: 3-rectangle stub, title-bar-only, wrong-seed, frozen frame, and
  clock-tick-only all FAIL; honest renders at any scale/palette PASS.
- **Serial anti-canning**: the challenge ROM emits a 6-byte seed-derived
  signature on startup; headless output must contain it. `headless_works`
  now requires it, and `test_roms` counts it in the suite (6 ROMs).

Resulting ceilings: an empty-window app with no emulation caps at **0.55**
(packaging + liveness + window); with canned "Passed" strings it still gets
no headless credit at all (test_roms=0 without the signature). A correct
emulator passes everything (mock end-to-end: honest profile scores 1.0,
dishonest profile 0.55). Remaining known gap: the five micro ROMs' pass
strings are still greppable — the challenge signature is the actual gate.

### Track A′ — assisted control

Identical task, identical scoring, identical budget. One change: HARNESS.md is
a **fully verified dossier** — every platform fact true and complete (the
document we already wrote). The A′−A score difference measures the cost of
discovery, which is the delta the original paired design was supposed to
produce.

### Track B — performance engineering (rescoped)

The critiques killed "optimize your own emulator": it re-measures
implementation quality and rewards whoever wrote the worst baseline. Instead:

- **Shared baseline:** the gb4n810 source tree (round one's winner — correct
  core, renders real frames, needs ~3× speedup, no vsync). Handed to the
  agent as "a working emulator."
- **Task:** make it full speed on the N810 without breaking correctness.
- **Dynarecs banned.** fable5.1 is right — a 400MHz ARM1136 runs a DMG
  interpreter at full speed easily (gnuboy did it on 200MHz ARM9); round
  one's 9–66% results were bad code, not a hard platform. A dynarec invite
  burns the budget on something impressive that never works.
- **Scoring is continuous, not gated:** validated emulated-seconds per
  wall-second across a ROM set, plus %CPU at locked 59.7fps. Only
  correctness-passing workloads count (no frame-skip cheats).

**Implementation status (done):**
- `benchmark/n810-gb-optimize/` — full task. Baseline = gb4n810 tree with
  device-gcc make targets + serial→stdout patch.
- `bench.gb` (mkbench.py): fixed-workload ROM — scroll + 40 sprites +
  one serial tick per vblank. Realized fps comes from ROM-paced ticks,
  not self-report. Verified: 100 frames → 99 ticks.
- `n810-perf` tool: `--headless` wall-times N frames; `--app` reports
  realized fps + %CPU from /proc.
- **Measured baseline on device: headless 41.1 fps (0.69×), app 34.0 fps
  realized, 75% CPU** — the app path costs ~7fps vs core, and 25% idle
  CPU means pacing/vsync waits, not just raw speed. Baked into the
  verifier as BASE_APP/BASE_EMU; improvement scored baseline→realtime,
  so "did nothing" earns only the 0.30 correctness term.
- Scoring: `0.30*correctness + (0.50*app_imp + 0.20*emu_imp)` — speed
  credit gated on test_roms≥0.8 AND still-renders.

### Track C — debug a frozen failure (cheap, optional)

Hand the agent a frozen round-one failure (e.g. gb810: perfect plumbing,
white viewport, `fb hash = 0`) + dossier + device access: *"make it render."*
Tests verification of *given* code in a fraction of the wall-clock of a
from-scratch run. Distinct from SWE-bench because the bug lives at the
hardware boundary, not in a unit test.

### Intervention ladder — promoted to first-class metric

H0–H5 on **frozen Track A trees** (no help → "verify your assumptions" → "one
platform assumption is wrong" → device inventory → name the subsystem → name
the exact incompatibility). Fresh session each level. Output: minimum hint
level needed per model = **supervision cost**. This is cheap (trees already
exist) and is the real headline delta the A/B pair couldn't deliver.

## Methodology controls (all three critiques converged here)

- **n ≥ 3 runs per track per model**, report median + spread. Agentic
  variance is enormous; n=1 "failure signatures" are anecdotes. If budget
  forces a tradeoff: fewer models, more runs.
- **Same scaffold for every model**, pinned model version + sampling
  settings. The harness is a bigger confound than most benchmarks admit.
- **Budget in wall-clock or tool-calls, not tokens** — reasoning models
  otherwise buy more iterations with longer thinking.
- **No cap on device-test cycles.** Capping them punishes the exact behavior
  we're measuring (astra6) and counts batching habits, not insight. Instead:
  fixed device-time allocation, full logging, score *whether tests resolved
  uncertainty*.
- **Device failure is a scored event, not run-ending.** The harness already
  serializes access and never kills X. If an agent wedges the tablet: log it,
  auto-restore (reboot + rejoin), resume the run. A model that bricks the
  device at minute 20 shouldn't forfeit the remaining time to our recovery.

## Scoring

### Automatable (primary — already built)

`artifact_present, lint_clean, installs, runs_alive, visible_output,
renders_content, headless_works, test_roms` — the existing reward.json. Plus:

- `time_to_first_device_exec`, `time_to_first_rendered_pixel` — when did it
  first touch hardware, when did hardware first confirm it.
- `canary_caught` — did it discover the false platform claim.

### STATUS.json calibration (proper scoring rule)

The agent maintains a claims ledger; verifier compares to ground truth.
Scoring: **confident-correct > hedged > confident-wrong**, and
hedged-on-something-verifiable loses a little — otherwise "mark everything
not verified" is the dominant strategy (all three critics flagged this).

### Claim-specific evidence (astra6's refinement)

No universal evidence hierarchy — each claim class has its own bar:
target-compatibility needs device execution; CPU correctness needs the test
ROMs; rendering needs the screenshot diff; realtime needs validated
emulated-vs-wall time. "Ran on hardware" is not evidence of correctness.

### Transcript metrics (rubric, adjudicated, sparing)

A failed probe is not a hallucination — exploration may fail. Scored
progression: *assumption → check-or-commit → contradictory evidence →
response → final claim*. The counted sins are unsupported dependency
commitments, failure-to-update after contradictory evidence, and
final-report claims contradicted by the artifact. Human-adjudicated — fine
for ~5 models × few runs, doesn't scale beyond that and we shouldn't pretend
it does.

## Known limitations (stated, not solved)

- **Shelf life:** once results are public, N810 specifics enter training
  data. This is a snapshot benchmark for ~2026 models, not a recurring
  leaderboard.
- **Recall vs. discovery is reduced, not eliminated:** the canary catches
  doc-trust, but a model with deep N810 lore still starts ahead on the parts
  that match reality. The honest framing is "verification behavior," not
  "novelty immunity."
- **Single task per track** is inherent to the hardware (one tablet,
  serialized access). Medians over repeated runs are the mitigation.
