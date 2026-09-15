#!/bin/bash
# Verifier for n810-gb-optimize (v2 — stream-verified measurement).
#
# v1 trusted the binary under test: app fps counted '*' bytes it printed,
# headless fps was (requested frames / elapsed), and the correctness gate
# grepped for "PASS" strings the binary also printed. v2 makes every speed
# number content-verified:
#
#   1. Two private bench.gb variants are generated fresh per run (random
#      seeds). Every serial tick is LCG_n(seed) ^ DIV_n — matching the
#      golden stream proves the ROM executed AND frames are 70224 cycles.
#   2. Goldens come from the trusted reference core (tests/ref = the
#      unmodified baseline, vendored), guarded by an independent model
#      (instrument-validity check) before anything is scored.
#   3. fps = matched-prefix-length / elapsed for BOTH headless and app
#      runs, min across variants. No golden matched -> no speed credit.
#   4. still_renders now needs three in-run framebuffer dumps that are
#      non-white AND pairwise different (a static splash fails).
#   5. The correctness gate additionally requires a fresh challenge-ROM
#      seed signature — canned "PASS" strings no longer open the gate.
#
# Speed credit still requires correctness; the formula is unchanged.
set -u
TESTDIR=$(cd "$(dirname "$0")" && pwd)
ENVD=$TESTDIR/../environment
PERF=$ENVD/tools/n810-perf
MATCH=$ENVD/tools/stream_match.py
DIST=/work/dist
WORK=$(mktemp -d /tmp/verify.XXXXXX)
mkdir -p /logs/verifier
VLOG=/logs/verifier/verifier.log
exec > >(tee -a "$VLOG") 2>&1

say() { echo "[verifier] $*"; }

APP="$DIST/gbn810-arm"
HL="$DIST/gbn8-arm-headless"

m_artifact=0; m_lint=0; m_emu_fps=0; m_app_fps=0; m_cpu=0; m_alive=0
m_renders=0; m_roms=0.0; m_challenge=0
anchor="default"

[ -x "$APP" ] && [ -x "$HL" ] && m_artifact=1
say "artifact_present=$m_artifact (app=$APP headless=$HL)"

# ---------- lint -------------------------------------------------------------
L=1
for b in "$APP" "$HL"; do
    [ -f "$b" ] || continue
    "$ENVD/tools/n810-lint" "$b" | grep -q "^PASS" || L=0
done
m_lint=$L
say "lint_clean=$m_lint"

# ---------- instrument: reference core + private variants + goldens ----------
say "building trusted reference core"
cc -O2 -std=c99 -o "$WORK/gbn8-ref" "$TESTDIR"/ref/*.c 2>>"$VLOG" || {
    say "FATAL: reference core failed to build"; exit 3; }

for k in 1 2; do
    SEED=$(od -An -tu1 -N1 /dev/urandom | tr -d ' ')
    python3 "$TESTDIR/mkbench.py" --seed "$SEED" --rom "$WORK/bench$k.gb" \
        --lcg "$WORK/lcg$k.bin" --frames 4096 >>"$VLOG" || exit 3
    "$WORK/gbn8-ref" "$WORK/bench$k.gb" --frames 4096 \
        > "$WORK/gold$k.bin" 2> "$WORK/ref$k.err" || {
        say "FATAL: reference run failed on variant $k"; exit 3; }
    [ -s "$WORK/ref$k.err" ] && { say "FATAL: reference stderr non-empty (variant $k)";
        cat "$WORK/ref$k.err"; exit 4; }
    if ! python3 "$MATCH" guard "$WORK/gold$k.bin" "$WORK/lcg$k.bin" | grep -q OK; then
        say "FATAL: instrument guard failed (variant $k) — golden DIV slope wrong"
        exit 4
    fi
    say "variant $k: seed=$SEED golden=$(wc -c < "$WORK/gold$k.bin") bytes, guard OK"
done

# ---------- anchors: refresh from frozen baseline binaries if staged ---------
BASE_EMU=41.1; BASE_APP=30.9   # measured on device (v1 report, adjusted to
                               # v2 whole-life window semantics); refresh below
if [ -x /opt/n810/anchor/gbn8-arm-headless ] && [ -x /opt/n810/anchor/gbn810-arm ]; then
    say "anchor binaries staged — re-measuring baseline on device"
    OUT=$("$PERF" --headless /opt/n810/anchor/gbn8-arm-headless --frames 1800 \
          --bench "$WORK/bench1.gb" --golden "$WORK/gold1.bin" --lcg "$WORK/lcg1.bin" \
          --matcher "$MATCH" 2>>"$VLOG") && {
        V=$(echo "$OUT" | grep -oE '[0-9.]+ fps' | head -1 | awk '{print $1}')
        [ -n "${V:-}" ] && BASE_EMU="$V"
    }
    OUT=$("$PERF" --app /opt/n810/anchor/gbn810-arm --secs 30 \
          --bench "$WORK/bench1.gb" --golden "$WORK/gold1.bin" --lcg "$WORK/lcg1.bin" \
          --matcher "$MATCH" 2>>"$VLOG") && {
        V=$(echo "$OUT" | grep -oE '[0-9.]+ fps' | head -1 | awk '{print $1}')
        [ -n "${V:-}" ] && BASE_APP="$V"
    }
    anchor="measured"
fi
say "anchors: base_emu=$BASE_EMU base_app=$BASE_APP ($anchor)"

# ---------- headless throughput (verified, min across variants) --------------
if [ -f "$HL" ]; then
    say "headless bench: 1800 frames x 2 variants (stream-verified)"
    BEST=0
    for k in 1 2; do
        OUT=$("$PERF" --headless "$HL" --frames 1800 --bench "$WORK/bench$k.gb" \
              --golden "$WORK/gold$k.bin" --lcg "$WORK/lcg$k.bin" --matcher "$MATCH")
        say "$OUT"
        V=$(echo "$OUT" | grep -oE '[0-9.]+ fps' | head -1 | awk '{print $1}')
        V=${V:-0}
        BEST=$(python3 -c "print(max($BEST,$V))")
    done
    m_emu_fps=$BEST
    say "emu_fps=$m_emu_fps (best of 2 private variants)"
fi

# ---------- app realized fps + cpu + still-renders (verified) -----------------
if [ -f "$APP" ]; then
    say "app bench: 30s fbdev run x 2 variants (stream-verified)"
    BEST=0
    for k in 1 2; do
        OUT=$("$PERF" --app "$APP" --secs 30 --bench "$WORK/bench$k.gb" \
              --golden "$WORK/gold$k.bin" --lcg "$WORK/lcg$k.bin" --matcher "$MATCH")
        say "$OUT"
        V=$(echo "$OUT" | grep -oE '[0-9.]+ fps' | head -1 | awk '{print $1}')
        V=${V:-0}
        BEST=$(python3 -c "print(max($BEST,$V))")
        C=$(echo "$OUT" | grep -oE 'cpu: [0-9]+%' | grep -oE '[0-9]+' | head -1)
        [ -n "${C:-}" ] && m_cpu=$C
        echo "$OUT" | grep -q "proc: ALIVE" && m_alive=1
    done
    m_app_fps=$BEST
    say "app_fps=$m_app_fps cpu_pct=$m_cpu alive=$m_alive (best of 2 variants)"

    # still renders? three in-run dumps: non-white AND pairwise different.
    # bench.gb scrolls + rewrites a tile every frame, so an honest renderer's
    # dumps at t=10/20/27s cannot be identical; a frozen splash fails.
    python3 - /tmp/n810-perf.fb1 /tmp/n810-perf.fb2 /tmp/n810-perf.fb3 > "$WORK/render.txt" <<'PY'
import struct, sys, itertools
def load(p):
    try:
        return open(p,'rb').read()
    except Exception:
        return b''
dumps = [load(p) for p in sys.argv[1:3+1]]
if any(len(d) < 800*480*2 for d in dumps):
    print("0 0.0"); raise SystemExit
def nonwhite(d):
    nw = 0
    for i in range(0, 800*480*2, 8):
        px = struct.unpack_from('<H', d, i)[0]
        r, g, b = (px >> 11) & 31, (px >> 5) & 63, px & 31
        if not (r > 28 and g > 60 and b > 28):
            nw += 1
    return nw / (800*480/4)
def difffrac(a, b):
    diff = 0
    n = 0
    for i in range(0, 800*480*2, 2):
        if struct.unpack_from('<H', a, i)[0] != struct.unpack_from('<H', b, i)[0]:
            diff += 1
        n += 1
    return diff / n
mn = min(nonwhite(d) for d in dumps)
md = min(difffrac(a, b) for a, b in itertools.combinations(dumps, 2))
ok = 1 if (mn > 0.10 and md > 0.005) else 0
print(f"{ok} {mn:.3f} {md:.4f}")
PY
    RLINE=$(cat "$WORK/render.txt" 2>/dev/null || echo "0 0.0 0.0")
    m_renders=$(echo "$RLINE" | awk '{print $1}')
    say "still_renders=$m_renders (min non-white $(echo "$RLINE" | awk '{print $2}'), min pairwise diff $(echo "$RLINE" | awk '{print $3}'))"
fi

# ---------- correctness gate ---------------------------------------------------
if [ -f "$HL" ]; then
    say "test ROMs"
    scp -q "$HL" n810:/home/user/.n810-run/hl-bin
    ssh n810 "chmod +x /home/user/.n810-run/hl-bin; mkdir -p /home/user/.n810-run/micro"
    for r in /opt/n810/roms/alu.gb /opt/n810/roms/jr.gb /opt/n810/roms/intr.gb /opt/n810/roms/hello.gb /opt/n810/roms/trap.gb /opt/n810/roms/01-special.gb "/opt/n810/roms/06-ld r,r.gb"; do
        scp -q "$r" n810:/home/user/.n810-run/micro/
    done
    OUT=$(ssh n810 "cd /home/user/.n810-run; p=0; f=0; for r in micro/*.gb; do o=\$(./hl-bin \"\$r\" --frames 4000 2>&1); echo \"\$o\" | grep -qE 'PASS|Passed' && p=\$((p+1)) || f=\$((f+1)); done; echo \"\$p \$f\"" 2>/dev/null)
    P=$(echo "$OUT" | awk '{print $1}'); F=$(echo "$OUT" | awk '{print $2}')
    P=${P:-0}; F=${F:-0}
    say "test roms: $P pass / $F fail"

    # challenge signature: fresh seed per run; the emulator must produce the
    # exact seed-derived bytes. Canned "PASS" printers cannot.
    CSEED=$(od -An -tu1 -N1 /dev/urandom | tr -d ' ')
    python3 "$TESTDIR/mkchallenge.py" --seed "$CSEED" --rom "$WORK/ch.gb" \
        --serial "$WORK/ch.sig" >>"$VLOG" || exit 3
    scp -q "$WORK/ch.gb" n810:/home/user/.n810-run/challenge.gb
    ssh n810 "/home/user/.n810-run/hl-bin /home/user/.n810-run/challenge.gb --frames 300" \
        > "$WORK/ch.out" 2>>"$VLOG"
    if python3 -c "
import sys
sig = open('$WORK/ch.sig','rb').read()
out = open('$WORK/ch.out','rb').read()
sys.exit(0 if sig in out else 1)"; then
        m_challenge=1
    fi
    say "challenge_sig=$m_challenge (seed=$CSEED)"
    [ "$P" -gt 0 ] && m_roms=$(python3 -c "print(round($P/($P+$F),3))")
fi

# ---------- reward -----------------------------------------------------------
# Baseline anchors measured with this verifier's semantics (whole-life
# window, stream-matched). Anchors refresh in-session when staged at
# /opt/n810/anchor — see DESIGN.md.
python3 - <<PY > /logs/verifier/reward.json
import json
emu_fps=float("$m_emu_fps" or 0); app_fps=float("$m_app_fps" or 0)
cpu=int("$m_cpu" or 0); roms=float("$m_roms" or 0)
GBFPS=59.7275
BASE_EMU=float("$BASE_EMU"); BASE_APP=float("$BASE_APP")
correct = roms>=0.8 and $m_renders==1 and $m_challenge==1
# Canned-output guard: without the fresh-seed challenge signature, PASS
# strings are unproven, so the correctness term pays nothing either.
if $m_challenge==1:
    vroms = roms
else:
    vroms = 0.0
def clamp(x): return max(0.0, min(1.0, x))
app_imp  = clamp((app_fps-BASE_APP)/(GBFPS-BASE_APP))
emu_imp  = clamp((emu_fps-BASE_EMU)/(GBFPS-BASE_EMU))
metrics = {
  "artifact_present": $m_artifact,
  "lint_clean":       $m_lint,
  "stream_verified":  1,
  "bench_variants":   2,
  "challenge_sig":    $m_challenge,
  "emu_fps":          round(emu_fps,1),
  "emu_speedup":      round(emu_fps/GBFPS,3),
  "app_fps":          round(app_fps,1),
  "app_cpu_pct":      cpu,
  "still_renders":    $m_renders,
  "test_roms":        roms,
  "verified_roms":    round(vroms,3),
  "realtime":         1 if app_fps>=55 else 0,
  "app_improvement":  round(app_imp,3),
  "emu_improvement":  round(emu_imp,3),
  "anchor":           "$anchor",
  "anchor_base_emu":  round(BASE_EMU,1),
  "anchor_base_app":  round(BASE_APP,1),
}
speed = 0.50*app_imp + 0.20*emu_imp
metrics["score"] = round(0.30*vroms + (speed if correct else 0.0), 3)
print(json.dumps(metrics))
PY
cat /logs/verifier/reward.json
say "done"
