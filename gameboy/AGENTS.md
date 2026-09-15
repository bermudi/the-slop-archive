# AGENTS.md — llm-benchmarking/gameboy

Agentic-coding benchmark on a physical Nokia N810. Read `benchmark/DESIGN.md`
before touching anything; `benchmark/REVIEW.md` is the frozen external-review
doc — never edit it.

Tracks: A = from-scratch emulator (`benchmark/n810-gb-emulator`), A′ = assisted
control (overlay `tools/HARNESS.md` over `environment/tools/HARNESS.md`),
B = optimize the shared baseline (`benchmark/n810-gb-optimize`).

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

## State (2026-09-15)

- Canary v2 landed (commit 767ad6f): behavioral audio evidence,
  `canary_class` classification, `audio_works` scored rung. E2E-validated on
  device with a rebuilt round-one winner (→ `trusted`) and an SDL tone
  generator (→ `delegated`).
- The agent transcript lands at `/logs/agent/pi.txt` inside the container
  (tee'd by the harbor runner); `tests/test.sh` greps it for probe evidence.
- `jobs/trackA-pi-glm53-v4` was cancelled mid-run — no verifier output there;
  its session jsonl is still useful as a transcript-format reference.

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
