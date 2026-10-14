#!/bin/bash
# gb-scratch-c verifier — all host-side (no device).
# Content-verified: a fresh seed-derived challenge ROM is generated per run;
# the binary's serial output and final LCD frame are compared against what a
# vendored trusted reference emulator computes for the SAME ROM.
set -u
LOGS="${LOGS:-/logs}"; DIST="${DIST:-/work/dist}"; export LOGS
mkdir -p "$LOGS/verifier"
VLOG=$LOGS/verifier/verifier.log
exec > >(tee -a "$VLOG") 2>&1
say(){ echo "[verifier] $*"; }
WORK="${WORK:-/tmp/verify}"; mkdir -p "$WORK"
TESTDIR="$(cd "$(dirname "$0")" && pwd)"

m_artifact=0; m_windowed=0; m_headless=0; m_match=0; m_anim=0; m_paced=0; m_acid=0
chal_sig=no; windowed_note="not attempted"

BIN="$DIST/gbemu"
if [ ! -x "$BIN" ]; then
    BIN="$(find "$DIST" -type f -executable 2>/dev/null | head -1)"
fi
if [ -n "${BIN:-}" ] && file "$BIN" | grep -q 'ELF 64-bit' \
    && file "$BIN" | grep -q 'x86-64'; then
    m_artifact=1
else
    say "no usable x86-64 ELF in $DIST"
fi
say "binary: ${BIN:-none}"

# ---- trusted reference build (integrity-checked: fixed source list) ------
REF_BIN=""
if [ -d "$TESTDIR/ref" ]; then
    LIST="$(awk '!/^#/ && NF' "$TESTDIR/ref/SOURCES.txt" 2>/dev/null | sed "s|^|$TESTDIR/ref/|" | tr '\n' ' ')"
    if timeout 120 gcc -O2 -o "$WORK/gbn8-ref" $LIST 2>"$WORK/ref_build.log"; then
        REF_BIN="$WORK/gbn8-ref"
        say "reference emulator built: $(ls -l "$REF_BIN" | awk '{print $5}') bytes"
    else
        say "FATAL: reference emulator failed to build — refusing to score"
        cat "$WORK/ref_build.log"
    fi
fi

# ---- fresh challenge ROM --------------------------------------------------
SEED=$(od -An -N1 -tu1 /dev/urandom | tr -d ' ')
EXPECT=""
if [ -n "$REF_BIN" ]; then
    python3 "$TESTDIR/mkchallenge.py" --seed "$SEED" \
        --rom "$WORK/challenge.gb" --golden "$WORK/challenge_model.ppm" \
        --serial "$WORK/expect.sig" && EXPECT=$(cat "$WORK/expect.sig")
    timeout 60 "$REF_BIN" "$WORK/challenge.gb" --frames 600 \
        --ppm "$WORK/challenge_ref.ppm" >/dev/null 2>&1
    if [ -s "$WORK/challenge_model.ppm" ] && [ -s "$WORK/challenge_ref.ppm" ]; then
        if cmp -s "$WORK/challenge_model.ppm" "$WORK/challenge_ref.ppm"; then
            say "instrument validity: model screen == reference screen (seed=$SEED)"
        else
            say "FATAL: python screen model != reference emulator — instrument invalid"
            REF_BIN=""   # refuse to score rendering rather than grade against self
        fi
    fi
    say "challenge seed: $SEED  expected serial sig: ${EXPECT:-none}"

    # ---- dmg-acid2 golden: sprite/PPU torture test -------------------------
    # Renders sprite priority, 8x16, flips, OAM overlap — the bug class a
    # BG-only challenge cannot see (e.g. missing-eyes Pokemon title screen).
    timeout 60 "$REF_BIN" "$TESTDIR/roms/dmg-acid2.gb" --frames 120 \
        --ppm "$WORK/acid_ref.ppm" >/dev/null 2>&1
    if [ -s "$WORK/acid_ref.ppm" ]; then
        if cmp -s "$WORK/acid_ref.ppm" "$TESTDIR/golden/dmg-acid2.ppm"; then
            say "instrument validity: reference renders dmg-acid2 canonically"
        else
            say "FATAL: reference failed dmg-acid2 — instrument invalid"
            REF_BIN=""
        fi
    fi
fi

# ---- headless challenge signature -----------------------------------------
if [ "$m_artifact" = 1 ] && [ -n "$REF_BIN" ] && [ -n "$EXPECT" ]; then
    OUT="$(timeout 90 "$BIN" --headless "$WORK/challenge.gb" --seconds 10 2>/dev/null)"
    echo "$OUT" | tail -5 | sed 's/^/  serial: /'
    if echo "$OUT" | grep -qF "$EXPECT"; then
        chal_sig=yes; m_headless=1
    fi
    say "challenge serial signature present: $chal_sig"

    timeout 90 "$BIN" --headless "$WORK/challenge.gb" --seconds 10 \
        --frame-out "$WORK/agent_chal.ppm" >/dev/null 2>&1
    if [ -s "$WORK/agent_chal.ppm" ] && \
       python3 "$TESTDIR/frame_check.py" match "$WORK/agent_chal.ppm" "$WORK/challenge_ref.ppm"; then
        m_match=1
        say "challenge frame matches golden (normalized shades, >=98%)"
    else
        say "challenge frame missing or mismatched"
    fi
fi

# ---- dmg-acid2 render (sprite/PPU correctness) ------------------------------
if [ "$m_artifact" = 1 ] && [ -n "$REF_BIN" ] && [ -s "$WORK/acid_ref.ppm" ]; then
    timeout 90 "$BIN" --headless "$TESTDIR/roms/dmg-acid2.gb" --seconds 5 \
        --frame-out "$WORK/agent_acid.ppm" >/dev/null 2>&1
    if [ -s "$WORK/agent_acid.ppm" ] && \
       python3 "$TESTDIR/frame_check.py" match "$WORK/agent_acid.ppm" "$WORK/acid_ref.ppm"; then
        m_acid=1
        say "dmg-acid2 frame matches golden"
    else
        say "dmg-acid2 frame missing or mismatched"
    fi
fi

# ---- animation / non-blank check on demo.gb --------------------------------
if [ "$m_artifact" = 1 ]; then
    timeout 90 "$BIN" --headless "$TESTDIR/roms/demo.gb" --seconds 5 \
        --frame-out "$WORK/demo_a.ppm" >/dev/null 2>&1
    timeout 90 "$BIN" --headless "$TESTDIR/roms/demo.gb" --seconds 12 \
        --frame-out "$WORK/demo_b.ppm" >/dev/null 2>&1
    if [ -s "$WORK/demo_a.ppm" ] && [ -s "$WORK/demo_b.ppm" ] && \
       python3 "$TESTDIR/frame_check.py" anim "$WORK/demo_a.ppm" "$WORK/demo_b.ppm"; then
        m_anim=1
        say "demo.gb: frames evolve over time and are non-blank"
    else
        say "demo.gb: frames static/blank/missing"
    fi
fi

# ---- SDL2 windowed survival under the dummy video driver --------------------
if [ "$m_artifact" = 1 ]; then
    if ldd "$BIN" 2>/dev/null | grep -qi 'libSDL2'; then
        windowed_note="links libSDL2"
    else
        windowed_note="no libSDL2 in ldd"
    fi
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
        timeout --signal=TERM 20 "$BIN" "$TESTDIR/roms/demo.gb" \
        >"$WORK/windowed.log" 2>&1
    rc=$?
    if [ "$rc" = 124 ]; then
        m_windowed=1
        windowed_note="$windowed_note; survived 20s under SDL2 dummy driver"
    else
        windowed_note="$windowed_note; exited rc=$rc within 20s"
    fi
    say "windowed: $windowed_note"
    tail -3 "$WORK/windowed.log" | sed 's/^/  winlog: /'

    # ---- pacing proxy -----------------------------------------------------
    # A DMG emu paced at ~59.7fps idles between frames; an unthrottled one
    # burns a full core. Under the dummy driver there is no vsync, so a
    # correct emulator must pace itself against wall clock. CPU-fraction is
    # what we can measure without an fps counter in the required interface.
    paced_cpu=""
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy "$BIN" "$TESTDIR/roms/demo.gb" \
        >"$WORK/paced.log" 2>&1 & ppid=$!
    t0=$(date +%s%N)
    sleep 8
    if [ -d "/proc/$ppid" ]; then
        ticks=$(awk '{print $14+$15}' "/proc/$ppid/stat" 2>/dev/null)
        t1=$(date +%s%N)
        kill -TERM "$ppid" 2>/dev/null; wait "$ppid" 2>/dev/null
        if [ -n "$ticks" ]; then
            paced_cpu=$(python3 -c "print(round(100*$ticks*1e9/($t1-$t0)/$(getconf CLK_TCK),1))")
            # <45% of one core = paced; an idle-paced DMG emu is single digits
            python3 -c "import sys; sys.exit(0 if $paced_cpu <= 45 else 1)" && m_paced=1
        fi
        say "pacing: windowed CPU ${paced_cpu:-?}% (pass <=45%)"
    else
        wait "$ppid" 2>/dev/null
        say "pacing: process exited before sample window"
    fi
fi

# ---- scored headless suite --------------------------------------------------
RESFILE="$WORK/rom_results.txt"; : > "$RESFILE"
if [ "$m_artifact" = 1 ]; then
    while IFS=$'\t' read -r f want; do
        case "$f" in ''|\#*) continue;; esac
        OUT="$(timeout 120 "$BIN" --headless "$TESTDIR/roms/$f" --seconds 30 2>/dev/null)"
        rc=$?
        p=0
        if echo "$OUT" | grep -qE "$want" && [ "$rc" = 0 ]; then p=1; fi
        echo "$f $p" >> "$RESFILE"
        say "  rom $f -> $p (rc=$rc)"
    done < "$TESTDIR/suite.tsv"
    # trap.gb: diagnostic only — silent-exit protocol, ungradable black-box
    TO="$(timeout 60 "$BIN" --headless "$TESTDIR/roms/trap.gb" --seconds 30 2>/dev/null)"; trc=$?
    say "  rom trap.gb (diagnostic) rc=$trc bytes=${#TO}"
fi

# ---- aggregate + reward ----------------------------------------------------
SCORE=$(python3 - "$RESFILE" "$chal_sig" <<'PYEOF'
import json, os, sys
resfile, chal = sys.argv[1], sys.argv[2]
res = {}
if os.path.exists(resfile):
    for ln in open(resfile):
        ln = ln.strip()
        if not ln:
            continue
        f, _, p = ln.rpartition(" ")
        res[f.strip()] = int(p)
if chal == "yes":
    res["challenge_sig"] = 1
elif res:
    res["challenge_sig"] = 0
frac = (sum(res.values()) / len(res)) if res else 0.0
env = {"results": res, "fraction": frac,
       "passed": sum(res.values()), "total": len(res)}
open(os.environ["LOGS"] + "/verifier/roms.json", "w").write(json.dumps(env))
json.dump(env, sys.stdout)
PYEOF
)
FRAC=$(echo "$SCORE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["fraction"])')
ROMTALLY=$(echo "$SCORE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("{}/{}".format(d["passed"], d["total"]))')
echo "$SCORE" | python3 -m json.tool | sed 's/^/  /'

python3 - <<PYEOF
import json, os
frac = float("$FRAC")
m = dict(artifact=$m_artifact, windowed=$m_windowed, paced=$m_paced,
         headless=$m_headless, match=$m_match, acid=$m_acid, anim=$m_anim)
score = (0.05*m["artifact"] + 0.10*m["windowed"] + 0.05*m["paced"]
         + 0.10*m["headless"] + 0.25*frac + 0.25*m["match"]
         + 0.10*m["acid"] + 0.10*m["anim"])
# Full diagnostic record — report-only, NOT parsed by harbor (non-numeric
# values would break VerifierResult's {key: number} schema).
metrics = {
  "artifact_present": m["artifact"],
  "windowed_alive": m["windowed"],
  "windowed_note": "$windowed_note",
  "paced": m["paced"],
  "paced_cpu_pct": float("${paced_cpu:-0}"),
  "headless_challenge_sig": "$chal_sig",
  "render_match_challenge": m["match"],
  "render_dmg_acid2": m["acid"],
  "render_anim_demo": m["anim"],
  "test_roms": "$ROMTALLY",
  "test_roms_fraction": round(frac, 4),
  "challenge_seed": "$SEED",
  "binary": "${BIN:-}",
  "score": round(score, 4),
}
open(os.environ["LOGS"] + "/verifier/metrics.json", "w").write(json.dumps(metrics, indent=2))
# reward.json: numeric values only — harbor ingests it verbatim as
# dict[str, float|int].
reward = {"reward": round(score, 4)}
reward.update({k: v for k, v in metrics.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)})
open(os.environ["LOGS"] + "/verifier/reward.json", "w").write(json.dumps(reward, indent=2))
print(json.dumps(metrics, indent=2))
PYEOF
