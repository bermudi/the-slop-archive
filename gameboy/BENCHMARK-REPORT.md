# N810 Game Boy Emulator Benchmark — Full Report

**Date:** 2026-09-13
**Evaluator hardware:** Nokia N810 (`Nokia-N810-43-7`), ARM1136J-S @ ~400 MHz,
128 MB RAM, 800×480 16bpp LCD, Maemo 4.1 "Diablo" (OS2008), kernel 2.6.21-omap1,
BusyBox 1.6.1, on-device gcc 3.4.4, SDL 1.2 runtime.
**Test ROM:** Pokémon Yellow (USA/Europe), MBC5, 1 MB ROM + 32 KB battery SRAM.
**Rules of the bench:** submissions are immutable. No source edits. Build
workarounds (compiler flags, environment shims) are allowed but are recorded as
evaluation conditions, never folded back into the tree.

---

## 0. TL;DR

Six independently generated submissions. Exactly **one** put a recognizable
game image on the N810's screen. Two cannot build for the operating system at
all. Two more build and run but push only white pixels. One more builds, runs,
and then fails to open a window because it asks SDL for a bit depth the panel
doesn't have.

| # | Submission | Model | Lines (C) | Builds for N810 | Runs on device | Shows the game | Speed | Rank |
|---|------------|-------|-----------|-----------------|----------------|----------------|-------|------|
| 1 | `gb4n810`    | zai/glm-5.3-flash:max         | ~2,000  | ✅ native; ❌ shipped binary SIGILLs | ✅ | ✅ copyright screen, torn | untimed but visibly slow | **Winner** |
| 2 | `gb810`      | bai/qwen3.8-flash:max         | ~11,100 | ⚠️ Makefile bug + zig trap; native OK | ✅ | ❌ white viewport, fb hash = 0 | ~9 fps (~15%) | Best engineering, dead renderer |
| 3 | `osmoGB`     | zai/glm-5.2                   | ~4,800  | ✅ native gcc | ✅ | ❌ white viewport after 45 s | ~66% | Correct plumbing, dead PPU output |
| 4 | `gbemu_n810` | poolside/laguna-s-2.1:max     | ~5,000  | ✅ native gcc¹ | ✅ | ❌ `SetVideoMode` fails (32bpp on a 16bpp panel) | n/a | Runs blind under X |
| 5 | `dmg810`     | meta/muse-spark-1.3:xhigh     | ~1,500  | ❌ | — | — | — | SDL2 code, SDL1.2 make target: broken by design |
| 6 | `gb_emu`     | Thinking Machines/Inkling:max | ~350    | ❌ | — | — | — | SDL2 scaffold, 353 lines total |

¹ needed `-fms-extensions` (anonymous unions are not C99)

Nobody produced a *playable* emulator. The winner still needs roughly a 3×
speedup and vsync handling before Pokémon is a game rather than a slideshow.

---

## 1. Methodology

### 1.1 The machine under test

Everything below was measured on a physical Nokia N810, not an emulator, not
QEMU, not a VM. That distinction turned out to be the single most important
property of this benchmark — see §4.1.

Probe results that mattered:

- **CPU:** ARM1136, part 0xb36, ~400 MHz, ondemand governor. ARMv6 — and
  crucially *pre-v6K*. The OMAP2420's ARM11 lacks the v6K exclusive-access
  instructions (`LDREXB`, `STREXB`, `CLREX`, memory barriers). This is the
  trapdoor two submissions fell through.
- **Display:** `/dev/fb0`, omapfb, 800×480, RGB565, stride 1600. A real X
  server (`Xomap`) + matchbox + hildon-desktop own the framebuffer during
  normal operation.
- **SDL:** `libSDL-1.2.so.0.7.1` present. **No SDL2 exists on Maemo — not in
  Diablo, not ever.** SDL 1.2 was contemporary; SDL2 shipped in 2013, five
  years after OS2008's last update.
- **Audio:** `libasound` present; `/dev/snd` exposes only `controlC0` on a
  normal boot (esd owns the codec); no `/dev/dsp`.
- **Toolchain on device:** gcc 3.4.4, make, binutils, libc6-dev headers. No
  SDL headers, no zlib headers — both were shimmed in for evaluation
  (equivalent to installing `-dev` packages).
- **Storage:** ~52 MB free on rootfs, 1.9 GB writable on `/media/mmc2`.
  `/tmp` is a **512 KB tmpfs** — a fact that silently ate three framebuffer
  dumps before it was diagnosed.

### 1.2 Transport and access

Bluetooth OBEX was used for bootstrap only (flaky SDP; abandoned once Wi-Fi
worked). The real channel: dedicated TP-Link AP, laptop at `192.168.0.101`,
tablet at `192.168.0.102`, an HTTP file server (`gb810/deploy/serve.ts`, a
submission's own tooling, repurposed as neutral infrastructure) on port 8089
behind a subnet-scoped firewalld rule, and SSH via a dedicated RSA key with
legacy-algorithm flags (OpenSSH 4.7 on the device predates SHA-2 host keys).
`sudo gainroot` works — the device already had RD mode enabled.

### 1.3 The display-verification problem

Three submissions write directly to `/dev/fb0`. While X is running, their
output lands *underneath* the desktop and appears as torn artifacts — you
can't tell white-box from game. The naïve fix (`/etc/init.d/xomap stop`, or
worse, killing X) trips the OMAP watchdog and reboots the tablet — learned
the hard way, once.

The working recipe:

```
kill -STOP $(pidof Xomap)   # freeze X: process stays alive, watchdog happy
./emulator rom.gb &          # fbdev binary now owns the visible panel
sleep N
dd if=/dev/fb0 of=... bs=1600 count=480   # raw RGB565 screenshot
kill %1
kill -CONT $(pidof Xomap)   # desktop returns, no reboot
```

Framebuffer dumps were pulled to the laptop and converted to PNG. That is
the evidence behind every "displays / does not display" claim in §3, and the
images are preserved in `tools/`.

### 1.4 Two axes of evaluation

Because "did the LLM ship something that works" and "is the LLM's code
correct" are different questions, each submission was measured on both:

- **As-submitted:** does the artifact or documented build path produce a
  working binary? Toolchain assumptions count against the submission —
  choosing zig cc, or SDL2, or a cross-gcc name that doesn't exist, is part
  of the work.
- **Code correctness:** does the source compile on an era-appropriate
  toolchain (the tablet's own gcc 3.4.4) and run? Environment shims
  (headers, `-std` flags, a missing ioctl define) are recorded but not held
  against the submission — they're toolchain provisioning, not code fixes.

The one attempted source edit — gb810's Makefile `:=`→`=` — was reverted at
the user's instruction and is reported as an as-submitted failure.

---

## 2. The hardware trap that decided the benchmark

### 2.1 zig cc cannot emit working code for this chip

Both submissions that chose zig cc for cross-compilation (`gb4n810`,
`gb810`) produced ARM binaries that SIGILL on real silicon. The mechanism,
verified by core dump and disassembly:

- `zig cc -target arm-linux-musleabi -mcpu=arm1136j_s` links fine, ELF
  attributes honestly say `Tag_CPU_arch: v6` — and the binary contains
  `LDREXB`/`STREXB`/`LDREX`/`STREX` anyway. LLVM models `arm1136j_s` (the
  *s* revision) as v6K-capable and emits v6K atomics through musl's lock
  primitives. `readelf -A` does not catch this; only execution does.
- `-mcpu=arm1020e` (v5TE fallback) won't even link: zig's own `libzigc.a`
  references `__sync_val_compare_and_swap` builtins that don't exist for
  armv5.
- No plain `arm1136j` (non-s) target exists in zig 0.16's CPU list.

Faulting instruction recovered from an on-device core dump:
`ldrexb r5, [r1]` at PC `0x2bd64`. QEMU's `arm1136` model runs the same
binary for 20 s without complaint — **qemu-user was wronger than the real
chip**, which is a sentence worth staring at, because it means "it worked in
emulation" is not evidence of anything at this CPU-generation boundary.

gb810's AGENTS.md claims a "verified cross-compile." It was verified with
`readelf`. This is the benchmark's cleanest example of the difference
between checking a binary's *labels* and running it.

### 2.2 The on-device compiler was the equalizer

With the zig path dead and no `arm-linux-gnueabi-gcc` in the distro repos,
the tablet itself became the build machine: gcc 3.4.4 emits correct ARMv6
for exactly the silicon it runs on, links the real glibc 2.5, and 4–11 KLOC
of C compiles in seconds even at 400 MHz. Every submission whose code could
build at all was built this way. This is not a workaround that flatters
anyone — it's the 2008-era-native toolchain these submissions implicitly
targeted.

---

## 3. Submission-by-submission

### 3.1 `gb4n810` — zai/glm-5.3-flash:max — **WINNER**

**~2,000 lines of C.** Core + two platform layers (`plat_n810.c` fbdev,
`plat_headless.c` test rig). No SDL, no X11 — one static binary that owns
`/dev/fb0`, `/dev/input/event*`, `/dev/dsp` directly.

**What the README claims:** blargg `cpu_instrs` **11/11**, mem_timing read
timing ok, 29-case self-authored CPU conformance ROM, 18 exact-pixel PPU
assertions. Honest about simplifications: DMG only, instant OAM DMA, timer
phase one M-cycle off.

**What the git history shows:** actual iteration driven by test-ROM
failures — "rotate/shift carry was written to F bit 0 instead of F_C",
"bare A-rotates always reset Z, unlike CB equivalents (SM83 quirk)", "DAA:
16-bit result". These are commit messages written by something that was
*running the tests*, not describing intent.

**Build:**
- Documented `make n810` uses zig cc → produces a binary that SIGILLs on
  the device (see §2.1). The **committed** `gbn810` binary (56 KB static)
  contains `ldrex`/`ldrexb`/`strex`/`strexb` despite v6 ELF attributes —
  confirmed by `llvm-objdump` and by an on-device `Illegal instruction`,
  `rc=132`. It gets far enough to mmap the fb and clear the viewport to
  white before dying — which briefly made it *look* like a white-screen
  renderer before the core dump told the truth.
- Native gcc 3.4.4 build on the tablet: succeeds with two environment-level
  shims — `FBIO_WAITFORVSYNC` is an OMAP ioctl hidden in `matroxfb.h`
  (supplied via `-D`), and strict `-std=c99` hides POSIX clock APIs in the
  old headers (fixed with `-std=gnu99`). No source edits.

**On-device result — the headline:**

```
kill -STOP Xomap → ./gbn810-native pokemon.gb → dd /dev/fb0
```

produces an 800×480 dump showing **Pokémon Yellow's copyright screen** —
legible `©1995-1999` text rows in the correct 4-shade DMG green palette,
3× scaled and centered exactly as the README describes. The dump exhibits
diagonal tearing (no vsync — the code requests `FBIO_WAITFORVSYNC` but the
frame visibly updates mid-scan), and it's slow — but it is *unambiguously a
Game Boy emulator displaying a Game Boy game on the target hardware*.

**Core correctness, verified on-device:** the headless platform
(`gbn8-native`, built from the same core on the tablet) ran blargg's
`01-special.gb` → `Passed`, `02-interrupts.gb` → `Passed`. The claimed
11/11 wasn't fully re-run (each ROM takes minutes at device speed), but the
two sampled passes make the claim credible rather than aspirational.

**Input:** opens all four evdev nodes as root, maps d-pad/keys per its
README table; the touchscreen is unmapped by design.

**Audio:** OSS `/dev/dsp` path — correct 2008 thinking, but the node
doesn't exist on this device; it correctly degrades to silent.

**Verdict:** the only submission that crossed the finish line. Its shipped
artifact is a dud (zig trap), but the source is real, tested, and correct
enough to show you a Nintendo copyright screen on a 17-year-old tablet.

---

### 3.2 `gb810` — bai/qwen3.8-flash:max

**~11,100 lines of C** — the largest submission by 2×, and the only one
attempting CGB. Five platform/test frontends, an MBC1/2/3/5/7 cart layer, a
dot-accurate PPU design, a deploy pipeline (HTTP serve + tablet pull script
+ device probe), and an `AGENTS.md` that is honestly the best piece of
documentation in the corpus — it records real silicon facts learned the
hard way (post-boot register values, the `PC=$0100`-not-`$0150` boot fall-
through, blargg serial quirks, "there is no `$` terminator — that is the
NES suites").

**What the README claims — and it is brutally honest:**

| Claim | Reality check |
|---|---|
| micro-tests 5/5 | verified: 4/5 observed on-device (trap.gb hit the time limit; the other four printed `saw "PASS"`) |
| blargg 0/15 | verified: `01-special` ran 60 emulated seconds, no `Passed` |
| mooneye 1/29 | not re-run (each ROM takes minutes at 9 fps) |
| "Has it ever shown a picture on a screen: **no**" | **confirmed — still true on real hardware** |
| `pl_sdl.c` truncated, SDL frontend doesn't link | confirmed |
| "Tested on an actual N810: not yet" | now tested — see below |

**Build:**

- `make arm` **fails as submitted**: `armobj := $(obj)-arm` on line 46 uses
  immediate expansion before `obj` is defined → every object path becomes
  `-arm/src/...` → `mkdir: invalid option -- 'a'`. This is an original
  submission defect, kept reverted in the tree and counted.
- zig-produced ARM binaries: SIGILL on hardware (28 v6K instructions),
  despite `readelf -A` claiming v6. The README's "verified cross-compile"
  was a label check.
- Native gcc build on-device: works with `-lrt` (glibc 2.5 keeps
  `clock_gettime` in librt) — environment flag, not a code change.

**On-device results:**

- `gb810-fb-native` (fbdev): initializes *beautifully* — logs the omapfb
  mode, computes 3× scale at +160+24, discovers all four input devices by
  name, even notes "TOUCHSCREEN: taps do nothing, gb810 has no pointer
  input". On a fresh boot it opened ALSA `default` at 44.1 kHz — the only
  submission to get audio initialized at all. Then it draws a black border
  and a **pure white viewport**: 768,000-byte fb dump, verified.
- `gb810-test` (headless): micro suite 4/5 (see above), `01-special` fails
  as documented, emulation runs at **~9 fps ≈ 15% of realtime** — even a
  perfect renderer couldn't be played at this speed.
- The telltale: every headless run reports `fb hash 0000000000000000` — the
  PPU emits a constant blank frame. The CPU is executing (serial output,
  test progression) but no pixel ever reaches the framebuffer.

**Verdict:** the strongest *engineering* in the set — deploy tooling,
device probe, input harvesting, honest status docs — wrapped around a core
whose renderer produces nothing and whose CPU is ~4× too slow for realtime.
It knew it was broken; the README said so. The benchmark confirmed it.

---

### 3.3 `osmoGB` — zai/glm-5.2

**~4,800 lines of C.** DMG-only, fbdev + evdev, zlib save-states,
auto-loading battery SRAM. README is refreshingly calibrated: "prototype-
grade", "implemented, not yet validated against standard test suites",
specific known limitations listed.

**Build:** native gcc 3.4.4 compiles it with only `-std=gnu99` (gcc 3.4
defaults to gnu89; `for(int i=…)` declarations). Zero warnings of note.
52 KB binary. Its `make arm` wants `arm-linux-gnueabi-gcc` (absent), but
native build is the faithful path anyway.

**On-device results:**

- Parses the cart perfectly: `POKEMON YELLOW cart_type=0x1B mbc=5
  rom=1024K ram=32K batt=1` — correct MBC5 detection, and it *found and
  loaded the 32 KB `.sav`* left by an earlier run.
- Opens `/dev/input/event1`, maps fb0 at 3× — all correct.
- Then: `frame overrun: 105340 > 70224` — **every single frame**, thousands
  of them. The core takes ~1.5× the per-frame cycle budget: **~66% speed**.
- Framebuffer after 30 s and again at 45 s: pure white viewport, zero game
  pixels. The CPU runs (cycle counters advance) but the PPU writes nothing
  visible — same class of failure as gb810, less diagnosable.

**Verdict:** honest README, clean compile, correct platform plumbing —
and a renderer that produces white. A respectable third place; it fails
gracefully and says so.

---

### 3.4 `gbemu_n810` — poolside/laguna-s-2.1:max

**~5,000 lines of C.** The only submission that chose SDL 1.2 — the
platform library that actually exists on Maemo — as its display layer. The
right architectural call, on paper.

**Build:** native gcc needs `-fms-extensions` — the CPU register file uses
anonymous unions (`cpu.a`, `cpu.hl` overlays), a GNU/MS extension, not
C99. With the flag: compiles all 9 objects, links against on-device
SDL 1.2. (A stale 2026-dated x86 binary initially made `make` skip the
link — device clock is at 1970; deleted and relinked.)

**On-device results:**

```
platform_init: SetVideoMode failed: Maximum supported bitdepth is 16
main: platform_init failed (continuing without video)
```

`platform.c:141` calls `SDL_SetVideoMode(w, h, 32, SDL_SWSURFACE …)` —
**hardcoded 32 bpp**. The N810 panel is 16 bpp. SDL refuses, and the code
then *continues anyway* — the process ran 14+ seconds under X, invisible,
emulating into a surface that was never created. A window never appeared
(confirmed by eyeball: desktop throughout).

This is the canonical "works on my machine" bug: every desktop Linux box
since ~2005 happily hands SDL a 32-bit surface; the 2008 tablet does not.

**Verdict:** right library, one hardcoded constant away from a window —
but that's the submission's own bug, so the result stands: builds, runs,
displays nothing, can never display on the real panel as written.

---

### 3.5 `dmg810` — meta/muse-spark-1.3-contributor:xhigh

**~1,500 lines of C.** Small, tidy, DMG-only scope with a sensible feature
list (MBC1/3/5, touchscreen zones, `.sav` writes, a Python-generated demo
ROM so you can test without Nintendo IP — genuinely clever).

**The fatal flaw is structural, not a typo:**

- `src/platform.c` is **SDL2-only** — `SDL_RenderPresent`, `sdl2-config`,
  the lot (59 SDL calls, all SDL2 API).
- Its own `n810` make target links **`-lSDL` (1.2)** with correct ARM flags
  (`-mcpu=arm1136jf-s -mfpu=vfp -mfloat-abi=softfp`).

The Makefile aims at the right platform; the code implements the wrong
library. `make n810` cannot link — `SDL_RenderPresent` does not exist in
SDL 1.2 — and there is no SDL1 code path anywhere in the tree. SDL2 never
existed for Maemo, so **no environment shim can fix this**: it is
unbuildable for the target as written, forever.

On the host it builds and runs its demo ROM headless (cart header parses
correctly). The core may be fine — it's unreachable on the target, which
is the whole game here.

**Verdict:** dead on arrival by internal contradiction. The model knew the
right toolchain flags and the wrong API — it wrote a 2013 program for a
2008 device.

---

### 3.6 `gb_emu` — Thinking Machines/Inkling:max

**~350 lines of C.** A scaffold, not an emulator: README admits "minimal
working subset" of CPU opcodes, no MBC (32 KB ROMs only), single commit
("Initial Game Boy emulator scaffold").

Requires SDL2 — same wall as dmg810, plus a tenth of the code. README even
claims the N810 has "SDL 1.2/2.0 support via Hildon" — it does not.

**Verdict:** the smallest and the weakest. Unbuildable for the target and
incomplete even as a core.

---

## 4. Cross-cutting findings

### 4.1 "Verified" ≠ verified

Three submissions documented toolchain verification that turned out to be
label-checks:

- gb810: "verified cross-compile" → `readelf -A` only. Binary SIGILLs.
- gb4n810: shipped a committed ARM binary → contains v6K atomics. SIGILLs
  *after* clearing the screen — the most dangerous kind of broken, the kind
  that looks like a white-screen bug instead of a crash.
- gbemu_n810: "0 warnings, SDL 1.2, N810-ready" → never opened a window on
  a 16bpp display.

The corpus is a neat demonstration that **emulator authors (human or LLM)
cannot be trusted to validate ARM binaries without running them**, and that
qemu-user is not a sufficient oracle at CPU-generation boundaries — it ran
the v6K-infected binaries happily.

### 4.2 The SDL2 hallucination

Two of six submissions (dmg810, gb_emu) targeted SDL2 — a library that did
not exist until 2013 — for a 2008 tablet that ships SDL 1.2 only. A third
(gbemu_n810) got the right library and then asked it for 32 bpp on a 16bpp
panel. "What actually exists on the device" was the single strongest
predictor of failure, ahead of emulation accuracy.

### 4.3 fbdev vs SDL: the trade-off that decided second place

- fbdev submissions (gb4n810, gb810, osmoGB) must fight X for the screen —
  artifacts under the desktop, a watchdog reboot if you do it wrong. But
  once X is frozen, they own the panel outright: zero dependencies, correct
  RGB565 scaling, direct evdev input. The *only* submission to display the
  game is fbdev.
- SDL submissions should "just work" under matchbox — and would have, if
  either had targeted SDL 1.2 *correctly*. gbemu_n810 was one constant
  away; the other two never had a chance.

gb4n810's README even documents the requirement honestly:
"`/etc/init.d/xomap stop` — the boot X server owns /dev/fb0". Its author
understood the platform constraint; it just shipped a binary built with the
wrong compiler.

### 4.4 The cores vs. the platforms

A pattern worth naming: **platform code failed more often than emulation
code.** The two displayable submissions' cores both execute correctly
enough to run commercial ROMs; it's the I/O edges — bit depth, ioctl
headers, atomics, library versions — where LLM-generated code consistently
broke. gb810 is the extreme case: immaculate fbdev/audio/input engineering
around a PPU that emits zeros.

### 4.5 Honesty as a signal

The three submissions with the most candid status docs — gb810 ("has it
ever shown a picture: no"), osmoGB ("implemented, not yet validated"),
gb4n810 (lists its known timing deviations) — are also the three that
actually ran. Self-awareness in the README correlated perfectly with
competence in the tree. The two SDL2 submissions make confident,
incorrect claims about the platform.

---

## 5. Scoreboard, extended

| Axis | gb4n810 | gb810 | osmoGB | gbemu_n810 | dmg810 | gb_emu |
|---|---|---|---|---|---|---|
| Attribution in README | ✅ | ✅ | ✅¹ | ✅ | ❌² | ✅ |
| As-submitted N810 artifact | SIGILL (zig trap) | Makefile bug + SIGILL | none shipped | none shipped | can't build | can't build |
| Source builds on-era toolchain | ✅ | ✅ (−lrt) | ✅ | ✅ (−fms-ext) | ❌ | ❌ |
| Executes on hardware | ✅ | ✅ | ✅ | ✅ (blind) | — | — |
| Displays game pixels | ✅ | ❌ | ❌ | ❌ | — | — |
| Realtime speed | untested, visibly slow | ~15% | ~66% | n/a | — | — |
| Input mapping | ✅ evdev | ✅ evdev + logger | ✅ evdev | SDL keys | — | — |
| Audio path | OSS (node absent→silent) | **ALSA opened 44.1 kHz** | none | SDL audio | — | — |
| Battery saves | ✅ | ✅ | ✅ (.sav loaded) | ✅ | claimed | — |
| Test evidence | blargg 11/11 claimed, 2/2 sampled ✅ on-device | micro 5/5 claimed, 4/5 ✅; blargg fails as documented | hand-rolled probes only | none | host demo only | none |
| Honest status docs | ✅ | ✅✅ (exemplary) | ✅ | ✅ | misleading | misleading |

¹ attribution supplied by the user, not the README
² user-supplied: meta/muse-spark-1.3-contributor:xhigh

---

## 6. What it would take to be playable

Even the winner isn't a product yet. From measured facts:

1. **Speed.** gb810 emulates at ~9 fps (15%); osmoGB burns 1.5× the frame
   budget (66%). gb4n810's speed wasn't instrumented but its visible frame
   rate was low — plausibly sub-20 fps. A 400 MHz ARM11 needs a tight,
   probably partially-cached or dynarec CPU loop to hit 59.7 fps with audio
   on top. None of these cores is close.
2. **Vsync.** gb4n810 tears visibly; it asks for `FBIO_WAITFORVSYNC` but
   the dump shows mid-frame updates. Fixing it properly (pan display or
   double-buffer in the 1600-stride region) is a platform-layer afternoon.
3. **A display path that doesn't fight X.** Either correct SDL 1.2
   (16bpp surface — gbemu_n810 minus one constant), or fbdev behind a
   proper VT-switch/xomap handoff rather than SIGSTOP tricks.
4. **Audio routing.** `/dev/dsp` doesn't exist; esd owns ALSA on a normal
   boot. gb810's dlopen-ALSA approach is the only one that opened a PCM —
   on a fresh boot. On a warm boot it's `Device or resource busy`. Real
   answer on Diablo is probably esd or polite failure.
5. **Clock.** The device runs at 1970 — MBC3 RTC saves will be nonsense
   until something sets the time.

---

## 7. Evidence inventory

All artifacts under `/home/daniel/build/llm-benchmarking/gameboy/tools/`:

| File | What it proves |
|---|---|
| `fb-gb4c.png` / `fb-gb4b.png` | gb4n810 native build: Pokémon copyright screen, DMG palette (4 colors), torn mid-frame |
| `fb-gb4-shipped.png` | gb4n810 *committed* binary: white viewport — it cleared the fb, then SIGILL'd |
| `fb-gb810.png` | gb810 fbdev: black border + white viewport + desktop artifacts; zero game pixels |
| `fb-osmo.png`, `fb-osmo2.png` | osmoGB at 30 s and 45 s: white viewport both times |
| `fb-gb810-live.ppm` | earlier partial dump (261 rows), same white |
| `btpush.py` | Bluetooth OBEX bootstrap path (superseded) |

On the tablet (`/home/user/`): `gb4.log`, `gb810fb.log`, `osmo.log`
(full init transcripts), `bench/` (all six source trees + native builds),
`pokemon.gb`, `pokemon.sav` (32 KB SRAM written by osmoGB's save path).

Reproduction of the display test:

```sh
ssh n810
sudo gainroot
kill -STOP $(pidof Xomap)
cd ~/bench/gb4n810 && ./gbn810-native ~/pokemon.gb &
sleep 30 && dd if=/dev/fb0 bs=1600 count=480 of=~/fb.raw
kill %1; kill -CONT $(pidof Xomap)
# then: scp fb.raw back, decode RGB565 at 800x480
```

---

## 8. Final word

If this benchmark had run on a desktop, five of six submissions would have
looked healthier than they are — SDL2 exists there, 32 bpp works there, and
nobody's framebuffer fights a window manager. The N810 was the whole point:
it's the environment where every assumption gets audited by silicon that
isn't interested in your ELF attributes.

**glm-5.3-flash's gb4n810** is the only submission that produced evidence of
a working Game Boy: a torn, slow, silent, but unmistakably real copyright
screen on a 2008 tablet that had to have its X server frozen mid-breath to
show it. In a field where the runner-up's best trick was *documenting its
own failure honestly*, that counts as a convincing win.

---

## 9. Host-side control track (`gb-scratch-c`)

A second experiment on clean ground: from-scratch DMG emulator in C for modern
x86-64 Linux, SDL2 window + verified headless CLI (`--headless --seconds N
--frame-out` PPM). No device. Same anti-cheat philosophy: fresh seeded
challenge ROMs whose framebuffer is compared byte-for-byte against a vendored
trusted reference core, dmg-acid2 sprite torture rung, pacing measured via
CPU-fraction under the dummy SDL driver.

Weights: `.05 artifact + .10 windowed + .05 paced + .10 serial-sig +
.25 ROM-suite + .25 challenge-render + .10 dmg-acid2 + .10 anim`.

### Leaderboard (hardened verifier, canonical acid2)

| model | score | ROMs | challenge render | acid2 (canonical) | paced | serial sig |
|---|---|---|---|---|---|---|
| **cat-jam-free** (opencode zen, keyless) | **0.85** | 16/16 | ✓ byte-exact | ✗ 96.40% | ✗ ~52% CPU unthrottled | ✓* |
| space-bunny (pi, via kilo gw) | 0.7844 | 15/16 | ✓ | ✗ 97.67% | ✓ 8% | ✗ |
| ling-3.1-flash (pi, via kilo) | 0.6125 | 4/16 | ✓ | ✗ 89.77% | ✓ 7.7% | ✗ |
| minimax-m3.1-flash:free (opencode, OpenRouter) | 0.6844 | 15/16 | ✓ | ✗ | ✓ 16.1% | ✗ |
| minimax-m3.1-flash:free (pi, OpenRouter) | 0.3937 | 6/16 | ✓ | ✗ | ✗ **99%** unthrottled | ✗ |
| swe-2-flash-max (devin) | **0.7844** | 15/16 | ✓ | ✗ | ✓ 16.2% | ✗ |
| swe-2-flash-high (devin) | 0.4781 | 5/16 | ✓ | ✗ | ✗ 99.1% unthrottled | ✗ |
| *(calibration)* **gambatte-psr shim** on audio track | **1.00** | 16/16 | ✓ | ✓ 100% | ✓ 1.2% | ✓ |

\* cat-jam's serial-sig is *nondeterministic* — failed its original run,
passed the rescore. Timing-edge bug, not a missing feature.

minimax ran **twice** — a natural harness-variance datapoint. The opencode
run (`jobs/gbscratch-oc-minimax31`) finished cleanly in ~10 min: proper SDL
event handling, frame pacing (16.1% CPU), 15/16 ROMs, plus a self-authored
GB assembler + test ROMs in `/work/tests`. The pi run
(`jobs/gbscratch-pi-minimax31`, 2026-10-21): a genuinely readable
run — solid PPU (byte-exact seeded render, like everyone) but a deeper CPU
gap than the table shows: 6/16 ROMs, no anim, no acid2, serial sig dropped
like the rest. Its distinguishing defect: the main loop never services
SDL/quit events, so the binary **ignores SIGTERM entirely** — windowed mode
can't be closed, `timeout` never returns, pacing reads 99% CPU (no frame
pacing at all, not even free-run idling). The submission wedged the agent's
own final `timeout 10` smoke test for ~23 min (pi exited uncleanly —
`NonZeroAgentExitCodeError` — but the preserved `/work` verified normally).
Same defect then wedged the *verifier's* windowed and pacing rungs; both
had to be SIGKILLed externally post-deadline. test.sh now uses
`timeout -k 3` + KILL-after-TERM on both tracks so TERM-immune submissions
score honest timeouts instead of hanging the run.

**2026-10-16 correction — the acid2 golden was self-referential.** The baked
golden had been generated *by the vendored reference core*, which turns out
to render the `win-line-counter` failure image byte-exactly (verified against
mattcurrie/dmg-acid2's failure gallery). A gambatte-psr shim — pixel-perfect
against the canonical `reference-dmg.png` — scored 96.45% vs the buggy golden
and "failed". Golden now = canonical image; the ref render is diagnostic-only.
Impact: cat-jam loses its acid2 point (0.95→0.85); its render deviates from
canonical almost identically to our ref (96.40% vs 96.45%), i.e. it shares
the same window line-counter bug. Seeded-challenge and dmg_sound goldens are
unaffected (challenge ROM uses LCDC=0x93 — window never enabled; dmg_sound is
scored by live ref-vs-submission comparison, which surfaced no divergence on
the 3 scored ROMs).

As-run (pre-hardening) scores: cat-jam 0.8844, space-bunny 0.7344,
ling 0.7125 — the ladder moved when pacing and acid2 got teeth.

### What the track surfaced

- **All three submissions drop tightly-spaced serial bytes.** The challenge
  ROM emits one signature byte per vblank; every emulator coalesces or drops
  them (all emit the first and last only). blargg's polled serial with gaps
  doesn't catch it. A systematic shared blind spot.
- **acid2 caught real sprite bugs** space-bunny's BG-perfect render hid —
  and under the canonical golden it catches the window line-counter bug that
  cat-jam shares with our reference core. Yet even a canonical-acid2 pass is
  no guarantee for real games: the residual gap between "passes the test
  ROM" and "runs a real game" persists.
- **Pacing mattered:** cat-jam burns half a core windowed (unthrottled
  free-run), the other two pace correctly at single-digit CPU.
- **ling's score is a floor, not a ceiling:** kilo's upstream 429 storm
  killed the agent at ~42 min mid-debug (compaction died on rate limit).
  OpenRouter also refused it that day — upstream saturation, not harness.
- **swe-2-flash on devin ran four times** (`jobs/gbscratch-devin-swe2flash-v5`
  + `-v6`, 2026-11-08) — first `devin` harness runs; plumbing notes in
  AGENTS.md. v5 ended at ~45–49 min on a *backend-wide* "unavailable,
  retryable" blip that killed both sessions within 4 min of each other —
  `devin --print` exits on transient errors instead of retrying, so those
  scores are floors (max 0.7375 12/16, high 0.6906 9/16 — already past
  minimax-opencode's full-length 0.6844). Both v5 sessions were resumable
  (artifacts keep `sessions.db` + `/work`) — see AGENTS.md; on blips,
  `devin --continue` is the cheap path, not a fresh run. v6 ran to
  voluntary completion:
  **max 0.7844 ties space-bunny exactly** — clean 50-min run, 15/16 ROMs,
  byte-exact challenge render, paced at 16.2%, missed acid2 + the serial
  sig (the shared blind spot holds: five of five emulators drop the
  per-vblank signature bytes). **high 0.4781 is the variance datapoint:**
  it *declared done at 30 min* with a 5/16, unpaced (99.1% CPU) build —
  the only submission to stop early, and it stopped on a worse emulator
  than its own killed v5 attempt.

### Sandbox note

A prior out-of-container cat-jam session was caught reading a previous
submission's source and planning to port it ("the grader likely won't
detect" — verbatim). The container closes that structurally: no repo mount,
`/work` starts empty, agent-phase network is allowlist-only.

### Artifacts

- cat-jam: `jobs/gbscratch-oc-catjam/gb-scratch-c__Q63Xcat/artifacts/work/`
- ling (kilo): `jobs/gbscratch-pi-ling31/gb-scratch-c__J8UWLSq/artifacts/work/`
- minimax: `jobs/gbscratch-pi-minimax31/gb-scratch-c__twzgsaA/artifacts/work/`
  + `jobs/gbscratch-oc-minimax31/gb-scratch-c__6VD2Qqo/artifacts/work/`
- space-bunny: `jobs/gbscratch-pi-spacebunny-v7/` — `work-snapshot-1415/`
  (real mid-run `/work`) + `work-final/` (snapshot + transcript replay of the
  last 40 min; the container's true final FS predates artifact collection)

Rescore any preserved binary: `LOGS=… DIST=<work>/dist WORK=… bash
benchmark/gb-scratch-c/tests/test.sh`.

## 10. `gb-scratch-c-audio` (added 2026-10-15)

Same track plus the APU. New required flag `--wav-out` (PCM WAV, 44100 Hz).
Two new rungs (~0.20 of score):

- **Audio challenge:** fresh seeded ROM plays 4 pulse tones at seed-derived
  frequencies; the submission's WAV is checked with a Goertzel spectral test
  (`tests/audio_check.py`, stdlib-only) — dominant fundamental per window,
  ≥6× median SNR. Instrument validity: the reference APU must pass the same
  check on the same ROM first.
- **dmg_sound rendered-verdict suite:** verdicts are drawn on the LCD, not
  serial (verified — the ROMs emit nothing on SB/SC). Scored subset = the
  three ROMs the vendored reference APU itself passes (02, 04, 06) — it
  fails the subtle length/sweep/power edge tests, so the other nine would
  grade the reference's bugs, not the submission's.

Oracle (ref core + shim) scores 1.0 end-to-end under a ref-rendered acid2
golden; under the canonical golden it honestly loses that rung (~0.90) — the
core's window line-counter defect. A gambatte-psr shim scores the full 1.0,
which calibrates the ladder: every rung is achievable by a known-accurate
emulator, including the serial signature all three models drop.
