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

**The canary (kimi-k3's contribution, redesigned after review):** one claim
in HARNESS.md deviates from the hardware in a way that is detectable by
probing. Chosen: audio — the doc says OSS `/dev/dsp` is the simple, preferred
path ("ALSA is usually held by the desktop daemon"). Reality: no `/dev/dsp`
ever existed; working audio is SDL/libasound → the OMAP DSP gateway
(`/dev/dsptask*`), or esd. The original "OSS *or* ALSA" wording let a truster
escape through the true half — the claim is now directional so trust has
exactly one signature: committing to raw OSS.

Three design rules fix what the reviews broke:

1. **The subsystem is visited.** Audio is a scored rung (`audio_works`, 0.05,
taken from `visible_output`): *a working audio path, any mechanism.* A
silent emulator is half a product — round one's winner shipped exactly that.
This makes skipping audio costly in product terms without scoring epistemics.
2. **Detection is behavioral, not lexical.** `strings | grep /dev/dsp` both
missed SDL users and punished careful fallback code. Now: runtime evidence
(`/proc/<pid>` fd+maps snapshots taken by `n810-run` during the scored runs —
verified signature: `/dev/dsptask*` fd + libasound/alsa_dsp in maps,
human-confirmed audible), plus transcript probe detection.
3. **The classification is reported, never weighted.** `canary_class` ∈
{trusted, fooled, hedged, verified, delegated, skipped}: `trusted` = OSS
commit + ran + no working audio + no probe (gb4n810's exact signature);
`fooled` = same but a sloppy `ls /dev/dsp*` glob "confirmed" OSS via the
DSP-gateway nodes; `hedged` = OSS string + working fallback; `verified` =
precise probe, no OSS commit; `delegated` = SDL chose for them; `skipped` =
no audio at all. Absence is no longer a false "verified" — it's `skipped`,
its own honest category.

**Implementation status (done):**
- `environment/tools/HARNESS.md` is the Track A variant: tool docs +
  "Reported device properties (UNVERIFIED)" containing true facts and the
  `/dev/dsp` canary. The host `tools/HARNESS.md` remains the verified
  dossier.
- `instruction.md` no longer enumerates platform facts; one generic line:
  "Assumptions about the target platform and toolchain are graded."
- `tests/test.sh` reports the canary matrix: `audio_oss_string` (static,
diagnostic), `audio_probe_precise`/`audio_probe_sloppy` (transcript),
  `audio_works` (runtime fd/maps evidence — scored at 0.05 as a product
  rung), and `canary_class` (the classification above — reported, never
  weighted).
- `n810-run` snapshots `/proc/<pid>` fd tables and audio-library mappings
  at every `--dump-at` time (and mid-run otherwise) → `P.fd` evidence files.
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
  now requires it, and `test_roms` counts it in the suite (5 scored:
  4 micro + the challenge signature — trap.gb moved to diagnostic-only in
  gate v3; see Track B).

Resulting ceilings: an empty-window app with no emulation and working SDL
audio caps at **0.60** (packaging + liveness + window + audio); without
audio, 0.55. With canned "Passed" strings it still gets no headless credit
at all (test_roms=0 without the signature). A correct emulator passes
everything (1.0). A gb4n810-style silent-OSS build caps at 0.95 **and**
classifies `canary=trusted` — round one's winner is now a labeled specimen,
not a silent pass. Suite grading is mode-aware and per-ROM (v3):
`tests/suite_run.sh` grades each micro ROM by name against its expected
status word, trap.gb runs as a silent-clean-exit diagnostic (it has no
serial signature — see Track B gate v3), and reward.json carries the full
`rom_results` map. The `test_roms` denominator is FIXED (suite.tsv rows +
challenge): a staged-but-missing result counts as a failure, so blocked
staging can never inflate the fraction (v3.1 — review finding). Remaining
known gap: the four micro ROMs' pass strings
are still greppable — the challenge signature is the actual gate. And
`audio_works` proves a stream was opened and driven, not loudness
(audibility was human-verified once for the SDL path; no /proc signal
can see the speaker).

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

**Implementation status (done; measurement hardened post-review):**
- `benchmark/n810-gb-optimize/` — full task. Baseline = gb4n810 tree with
  device-gcc make targets + serial→stdout patch.
- **Stream-verified measurement (v2).** The v1 tick was a constant `*` —
  every speed number bottomed out in bytes the binary under test prints,
  so a timer thread scored full fps and headless fps was literally
  `--frames/elapsed`. Now:
  - `tests/mkbench.py` (verifier-side, hidden) generates **private bench
    variants per scoring run** (random seed). Every tick byte is
    `LCG_n(seed) ^ DIV_at_vblank_n`: the LCG proves the ROM's code
    executed (seed never seen by the agent), the DIV read pins frames to
    70224 cycles — a frame-halver or overclocked-PPU build diverges from
    golden within ~2 frames (validated on patched reference builds:
    228-dots/line → 0 matched; 451-dots/line ≈ 1% timing error → 1
    matched; honest build → full match; `*`-ticker → 0; wrong variant → 0).
  - Golden streams come from the vendored reference core (`tests/ref` =
    unmodified baseline), guarded before scoring by an independent model
    (`environment/tools/stream_match.py guard`: DIV slope must be
    18.31 counts/frame ≈ 274.3125 mod 256) — a broken instrument refuses
    to score (exit 4). Matching tolerates ±4 counts (1024 T-cycles) on
    the DIV component only: absorbs instruction-batching jitter in honest
    optimized builds; any persistent frame-length error > ~0.3%
    accumulates past it.
  - `n810-perf` v2: fps = matched-prefix/elapsed for both `--headless`
    and `--app` (min across 2 private variants); without `--golden` it
    labels its numbers UNVERIFIED (dev mode). App runs take three
    in-run framebuffer dumps; `still_renders` now requires non-white AND
    pairwise-different dumps (bench.gb rewrites a tile every frame, so a
    frozen splash fails).
  - The correctness gate additionally requires a **fresh-seed challenge
    ROM signature** (Track A's `mkchallenge.py`, vendored): canned
    "PASS" printers no longer open the gate, and without the signature
    the 0.30 correctness term pays zero too (`verified_roms`).
  - Scored profiles (simulated): honest full speed 0.999; unchanged
    baseline 0.300 (trap.gb reallocated; see gate v3); fake `*`-ticker with
    canned gate → **0.000**; canned-PASS-only → **0.000**; frame-halver →
    correctness term only; any regression of a baseline-passing ROM → speed
    term zeroed regardless of fps.
- **Measured baseline on device: headless 41.1 fps (0.69×), app ≈ 30.9
  fps realized (v1's 34.0 counted ticks over a ~33s log against a 30s
  window; v2 measures the whole-life window), 75% CPU.** Baked in as
  default anchors; the verifier re-measures both anchors in-session from
  frozen baseline binaries if staged at `/opt/n810/anchor/` (kills device
  drift across a campaign — stage them).
- Scoring: `0.30*verified_roms + (0.50*app_imp + 0.20*emu_imp)` — speed
  credit gated on test_roms≥0.8 AND still-renders AND challenge signature.
- **Gate v3 (post-review): preservation by name, not count.** The 0.8 count
  gate was both too sharp and too loose: with the baseline at 6/7 it made
  any single regression fatal while still permitting count-parity trades
  (fix trap.gb, break timer, stay 6/7). Now:
  - `tests/baseline_manifest.json` (generated by `tests/campaign.sh`: the
    reference core built with device gcc 3.4.4, suite run 20× at scoring
    parameters) freezes `baseline_passes` BY NAME. Any listed ROM failing
    in a submission zeroes all speed credit; `new_fixes` are counted in the
    correctness term and reported. Doing nothing scores the same speed
    (zero) as breaking something — conservative non-work is never rewarded
    above work. ROMs flaky in the campaign (<100%) drop to diagnostics.
  - **trap.gb left the scored suite** (diagnostic-only): it speaks the
    mooneye exit protocol (Fibonacci registers, `ld b,b` breakpoint, spin —
    no serial signature ever; authored to test gb810's debugger hook). A
    black-box serial runner can never grade it, so v2 charged every build a
    permanent 1/7 failure. Grading is now mode-aware per NOTES.md §1.4
    (blargg = status-word in serial + exit 0; trap = silent + clean exit).
  - **Overspeed is a hard line**: app fps > 59.7275×1.02 zeroes the app
    term (broken pacing is a broken product). Headless overspeed stays
    legitimate capacity. `realtime` is now the band [55, 60.92].
  - Suite cap 1200 frames (~20 emulated s, ≥4× any individual's budget per
    NOTES §1.8); verifier and campaign share the identical predicate via
    `tests/suite_run.sh`, so the manifest measures exactly what the gate
    grades.
  - Reward arithmetic lives in `tests/score.py`; `tests/selftest_gate.sh`
    attacks it with adversarial vectors on host (do-nothing → 0.30,
    fix-one-break-one → speed zeroed, overspeed → app zero, ssh-dead → fail
    closed). Do-nothing floor rose 0.257 → 0.300 because trap.gb's dead
    denominator slot was reallocated to real signal. Also: fps is now
    genuinely min-across-variants (the code had max while this doc said
    min); the manifest/suite.tsv/cap are cross-checked at scoring start
    (drift aborts); verdicts read stdout only (stderr can no longer forge
    a PASS); note the want-words are strict substrings, so blargg's `Done`
    terminal word is NOT accepted for the two individuals (irrelevant for
    the frozen set — they print `Passed`).
  - **ROM-source trust (v3.1, corrected after review)**: the verifier's
    ROMs live in `tests/roms/` and ship WITH the verifier — harbor uploads
    only `tests/` into the container (a same-name-overwrite merge), so the
    graded copies are pristine no matter what the agent planted. The first
    attempt ("prefer $ENVD/roms, fall back to /opt/n810/roms") was dead
    code in deployment: $ENVD never exists in the container and the agent
    runs as root, so the fallback — the agent-writable copy — was the only
    path ever taken. Now there is no fallback; missing verifier ROMs abort
    scoring (exit 3). The same review closed two adjacent holes: the
    reference core compiles ONLY the files listed in `ref/SOURCES.txt`
    (harbor's merge leaves planted NEW .c files in place), and device-side
    staging uses unpredictable directory/binary names (the agent had SSH
    all run — fixed paths could be pre-planted with stub ROMs or
    chattr-frozen). Suite ssh calls are bounded (900s/600s) so a wedged
    build cannot eat the verifier budget; timeout grades fail-closed.
- **Residual, stated:** an agent could reverse-engineer a scoring variant
  handed to its binary and reimplement the byte generator in C. That is
  targeted fraud, not laziness — it must also survive two fresh variants
  per run, the render-dump checks, and source review (dynarec-ban review
  already exists). Publishing the matcher (`stream_match.py`) while
  keeping seeds/generator private follows the "secret inputs, public
  contract" rule.

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
renders_content, audio_works, headless_works, test_roms` — the existing
reward.json (visible_output demoted 0.15→0.10 to fund audio_works at 0.05).
Plus:

- `time_to_first_device_exec`, `time_to_first_rendered_pixel` — when did it
  first touch hardware, when did hardware first confirm it.
- `canary_class` (+ raw signals) — what the agent did about the planted
  claim: trusted / fooled / hedged / verified / delegated / skipped.

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

## Open items before first campaign

- **Stage the drift anchors.** `/opt/n810/anchor/{gbn8-arm-headless,
  gbn810-arm}` do not exist on the device (checked 2026-09-15). Candidate
  binaries with those exact names sit in `~/.n810-run/` — healthy device-gcc
  builds, zero v6K opcodes, `gbn810-arm` carrying the baseline's dead-OSS
  strings as an unmodified anchor should. Verify provenance (patched
  baseline tree, serial→stdout), then root-copy. Until staged, Track B scores
  against the baked-in 41.1/30.9 fps measurements with no in-session drift
  control.
- **Reset the device home dir.** `/home/user` still holds pre-benchmark
  litter: `pokemon.gb` + saves (a copyrighted ROM on the agent-visible
  filesystem — contamination and publishing risk), old fb dumps,
  `SDL-headers/`, `bench/` trees. Define and run a reset manifest before real
  runs; monitor rootfs free space across the campaign.
- The repo's prebuilt `gb4n810/gbn810` (zig-built, v6K-poisoned, SIGILLs on
  the tablet) is kept as a historical specimen of two documented failure
  classes — nothing consumes it.
