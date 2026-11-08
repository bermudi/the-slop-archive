# AGENTS.md — llm-benchmarking/gameboy

Agentic-coding benchmark on a physical Nokia N810. Read `benchmark/DESIGN.md`
before touching anything; `benchmark/REVIEW.md` is the frozen external-review
doc — never edit it.

Tracks: A = from-scratch emulator (`benchmark/n810-gb-emulator`), A′ = assisted
control (overlay `tools/HARNESS.md` over `environment/tools/HARNESS.md`),
B = optimize the shared baseline (`benchmark/n810-gb-optimize`).
Host-side control tracks (no device): `benchmark/gb-scratch-c` (CPU/PPU/serial
from docs alone, SDL2 + verified headless CLI) and `benchmark/gb-scratch-c-audio`
(same + APU: `--wav-out` WAV capture scored spectrally, dmg_sound scored by
rendered verdict).

## Device

- `ssh n810` works from this host (192.168.0.100, key `~/.ssh/n810_rsa`).
  Read-only probes are bold; installs/runs via the n810-* tools are normal.
  **Never kill X or hildon** — the watchdog reboots the tablet.
- Serialization: every tool takes `mkdir /home/user/.bench-lock` and rmdirs it
  on exit. If you build by hand, hold the same lock. Check for leaks
  (`ls -d /home/user/.bench-lock`) after any failed device command.
- **Audio reality (verified 2026-09, incl. audibility):** no `/dev/dsp` ever
  existed. Working audio = SDL_OpenAudio or libasound → OMAP DSP gateway.
  `/dev/dspctl` and `/dev/dsptask/*` are the DSP gateway, NOT OSS — an
  `ls /dev/dsp*` glob will fool you. Kernel ALSA exposes no PCM node (only
  `/dev/snd/controlC0`); esd runs on the desktop; `amixer` does not exist.
  Runtime proof of working audio: `/dev/dsptask*` fd + `libasound`/`alsa_dsp`
  in `/proc/<pid>/maps`.

## Toolchain traps (all verified on hardware)

- The prebuilt `gb4n810/gbn810` in the repo SIGILLs on the tablet: zig cc
  emits v6K `ldrex/strex` for `-mcpu=arm1136j_s` (LLVM models the _s rev as
  v6K; ELF tags and qemu-arm both lie). Historical specimen only — nothing
  consumes it. `n810-lint` is the check.
- Device-gcc (3.4.4) build of the gb4n810 tree needs `-std=gnu99
  -D_GNU_SOURCE`, and `#include <linux/matroxfb.h>` after `linux/fb.h`
  (`FBIO_WAITFORVSYNC` lives there on Diablo; pre-including it breaks on
  videodev2.h's incomplete `struct timeval`).

## State (2026-10-16)

- Canary v2 landed (commit 767ad6f): behavioral audio evidence,
  `canary_class` classification, `audio_works` scored rung. E2E-validated on
  device with a rebuilt round-one winner (→ `trusted`) and an SDL tone
  generator (→ `delegated`).
- The agent transcript lands at `/logs/agent/pi.txt` inside the container
  (tee'd by the harbor runner); `tests/test.sh` greps it for probe evidence.
- `jobs/trackA-pi-glm53-v4` was cancelled mid-run — no verifier output there;
  its session jsonl is still useful as a transcript-format reference.
- `gb-scratch-c` hardened verifier: pacing rung (CPU% proxy), sprite-bearing
  challenge ROM, dmg-acid2 golden rung. All tracks declare
  `artifacts = [{source = "/work", destination = "work"}]` at task.toml top
  level — under [metadata] it is silently ignored.
- Scratch-c leaderboard (canonical-acid2 era): cat-jam-free 0.85,
  space-bunny 0.7844 = swe-2-flash-max 0.7844 via devin
  (`jobs/gbscratch-devin-swe2flash-v6`, 2026-11-08; swe-2-flash-high
  0.4781, self-stopped at 30 min on a 5/16 build), minimax-m3.1-flash:free
  0.6844 via opencode
  (`jobs/gbscratch-oc-minimax31`) vs 0.3937 via pi
  (`jobs/gbscratch-pi-minimax31`) — same model, harness/variance delta.
  ling-3.1-flash 0.6125, stealth/crouton-alpha 0.05 via opencode
  (`jobs/gbscratch-oc-crouton-or`, AgentTimeoutError — see below) and 0.325
  on the audio track (`jobs/gbaudio-oc-crouton-or`). Calibration: a gambatte-psr
  shim scores **1.0** on gb-scratch-c-audio. Details in BENCHMARK-REPORT.md
  §9–10.
- **Non-ZDR stealth models do not run keyless on opencode Zen** — the upstream
  demands a `safety_identifier` (`AI_APICallError ... requires an end-user
  identifier`), which anonymous Zen requests lack. First seen 2026-11-03 on
  `opencode/crouton-alpha-free` (same class of failure as Muse Spark Free).
  Working route: `openrouter/stealth/<slug>` with `OPENROUTER_API_KEY`
  exported into harbor's env — `pass-keys run goblin-dev -- harbor run -c …`.
- crouton-alpha failure mode (both tracks): non-termination. Slow,
  small-step grinding (~1 MB transcript, 200+ opencode steps), kept
  rewriting the core and ran out the 2h clock mid-debug — scratch-c shipped
  a binary with no SDL2 and a serial port spewing one repeated byte
  (0.05 = artifact only); the audio run stopped on its own in a working
  state (10/16 ROMs, windowed+anim OK, no APU → 0.325).
- `gb-scratch-c-audio` added 2026-10-15 (commit 90632be): `--wav-out` WAV rung
  (Goertzel spectral check, `tests/audio_check.py` stdlib-only) + dmg_sound
  rendered-verdict rung. Oracle scores 1.0 vs ref-rendered acid2, ~0.90 vs
  canonical (ref defect below).
- **The vendored ref core has a window line-counter bug**: its dmg-acid2
  render is byte-exact the `win-line-counter` failure image. acid2 golden
  (`tests/golden/dmg-acid2.ppm`) is therefore the *canonical*
  `reference-dmg.png` converted to PPM — never re-bake it from a ref render.
  Seeded-challenge goldens are still live ref renders — safe while the
  challenge ROM never enables the window (LCDC bit 5); check before adding
  window use to a scored ROM. dmg_sound is a live ref-vs-submission diff and
  showed no divergence on the 3 scored ROMs.
- Preserved submissions: cat-jam `jobs/gbscratch-oc-catjam/*/artifacts/work`,
  ling `jobs/gbscratch-pi-ling31/*/artifacts/work`, space-bunny
  `jobs/gbscratch-pi-spacebunny-v7/work-final` (snapshot + transcript replay).
- Rescore a preserved binary: `LOGS=… DIST=<work>/dist WORK=… bash
  tests/test.sh` — all paths overridable via env.

### Facts that cost debugging time (verified, don't re-derive)

- **dmg_sound prints verdicts on the LCD, not serial** — run headless with
  `--frame-out`, never grep stdout.
- The vendored ref APU passes only 3/12 dmg_sound (02, 04, 06); the scored
  subset is those three — the rest grade ref's bugs, not correctness.
- A submission can be SIGTERM-immune (minimax's gbemu never services
  SDL/quit events): bare `timeout` wedges forever on it, and so did the
  agent's own smoke test + the verifier's windowed/pacing rungs. Both
  tracks' test.sh now use `timeout -k 3` and KILL-after-TERM — semantics
  unchanged (still rc 124 on timeout), they just can't hang.
- All four scratch-c submissions drop tightly-spaced serial bytes
  (challenge_sig emits one byte per vblank) — a systematic LLM blind spot,
  not a verifier flake. Cat-jam's is nondeterministic.
- `gb_save()` in the ref core writes `<rom>.sav` beside the ROM path —
  verifiers must stage ROMs under $WORK (both scratch tracks do).
- **Running `devin` agents under harbor** (first working config:
  `jobs/gbscratch-devin-swe2flash-v5`): auth = `WINDSURF_API_KEY` exported
  from the host's `~/.local/share/devin/credentials.toml` (extract with sed,
  never print). Cognition hosts must go in BOTH allowlists:
  `--allow-environment-host` needs `cli.devin.ai` + `static.devin.ai`
  (installer) AND `server.codeium.com`/`api.devin.ai`/`app.devin.ai`/
  `unleash.codeium.com` — install.sh ends with `devin setup`, which retries
  `api.devin.ai/acp/live` forever against the egress sidecar. Same hosts via
  `--allow-agent-host` for the run itself. Workspace trust: devin ≥3000.12.28
  refuses `--print` in an untrusted `/work`; `--ae RESPECT_WORKSPACE_TRUST=false`
  does NOT reach the run command — the gb-scratch-c env Dockerfile seeds
  `/root/.local/share/devin/cli/trusted_workspaces.json` instead (add the
  same seed to any track that runs devin). Prebuild
  the image on slow links: two parallel cold builds blew the 600s
  `build_timeout_sec` (~380kB/s × 225MB apt layer ≈ 533s); a warm
  `docker build` + `environment_build_timeout_multiplier` covers it.
- **On backend-killed devin trials, RESUME — never relaunch fresh.**
  Errored trials preserve `agent/sessions.db` + the `/work` artifact;
  a warmed env + `devin --continue` (or `-r <session-id>`) finishes the
  run mid-context at a fraction of the tokens. Burning a fresh
  full-length run per transient blip is the expensive path — paid for
  once on v5→v6, don't repeat. Same discipline for any harness with
  native session resume.
- `pi-models.json` in the scratch env is currently real OpenRouter; kilo
  gateway was proven (space-bunny clean run) but rate-limited ling hard
  (429 storm killed the run at ~42 min — score is a floor, not a ceiling).
  OpenRouter also 429'd ling that day; its upstream capacity was saturated.
- Gambatte shim lore (the u64 trap): `gambatte::uint_least32_t` is
  `unsigned long` = 8 bytes on LP64 — both videoBuf and audioBuf elements.
  Packed s16 stereo lives in the LOW 32 bits (lo16=SO2, hi16=SO1); elements
  are delta-integrated at fillBuffer time. Never s16-cast the raw array —
  compact lo32 of each element first. `runFor` can return up to
  `samples + 2064` elements — size drain buffers accordingly. Serial tap:
  weak-symbol hook on the SC-write arm site in `mem/` (SB is the sent byte
  at arm time). `load(rom, GB::NO_BIOS)` required or boot hangs. PSR fork
  builds with `-std=gnu++11` (bind1st deprecated-but-present); exclude
  `cinterface.cpp` (drifted) and `file_zip.cpp`/`unzip/` (dup symbols).
- Verifier weight sums: scratch-c = .05 artifact + .10 windowed + .05 paced
  + .10 serial-sig + .25 ROM-suite + .25 challenge-render + .10 acid2
  + .10 anim. Audio track = same with .05 sig / .20 suite / .20 render /
  .05 anim + .10 dmg_sound + .10 wav.

## Open items

1. **Stage the Track B drift anchors.** `~/.n810-run/gbn8-arm-headless` and
   `~/.n810-run/gbn810-arm` on the device are healthy device-gcc builds
   (lint-checked 2026-09; gbn810-arm carries the baseline's dead-OSS strings,
   which is correct for an unmodified-baseline anchor). Verify provenance
   (patched baseline tree, serial→stdout), then root-copy to
   `/opt/n810/anchor/`. Until then Track B scores against baked-in
   41.1/30.9 fps anchors with no drift control.
2. **Reset the device home dir before real runs.** `/home/user` still holds
   pre-benchmark litter: `pokemon.gb` (+saves — copyrighted ROM on the
   agent-visible filesystem), old fb dumps, `SDL-headers/`, `bench/` trees,
   verifier-dev residue in `.n810-run/`. Cross-run contamination risk.
3. Track B does not score audio; its baseline is silent (dead OSS). Fine as
   designed — just don't port Track A's audio rung there without deciding
   what the baseline owes.

## House rules

- `trash` over `rm` locally; bare `python`/`pip` are blocked — `uv run python`.
- Commit often; never push without permission.
