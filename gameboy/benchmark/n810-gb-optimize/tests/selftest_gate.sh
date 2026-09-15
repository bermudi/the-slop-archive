#!/bin/bash
# selftest_gate.sh — adversarial vectors for the v3 gate (host-only, no device).
#
# Each case is a synthetic score.py input standing in for a class of
# submission. Expected values are derived by hand from DESIGN.md; the test
# fails loudly if the gate ever pays a cheater or starves an honest build.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d /tmp/gateself.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

# Fixture manifest: the measured-shape the campaign emits. Suite = 6 scored
# ROMs, baseline passes all six, trap.gb diagnostic.
cat > "$TMP/manifest.json" <<'EOF'
{
 "runs": 20, "frame_cap": 1200,
 "hl_bin": "fixture", "hl_hash": "fixture",
 "suite": ["alu.gb","jr.gb","intr.gb","hello.gb","01-special.gb","06-ld r,r.gb"],
 "diagnostics": ["trap.gb"],
 "baseline_passes": ["alu.gb","jr.gb","intr.gb","hello.gb","01-special.gb","06-ld r,r.gb"],
 "flaky": [],
 "per_rom": {}
}
EOF

ALLPASS='"alu.gb":1,"jr.gb":1,"intr.gb":1,"hello.gb":1,"01-special.gb":1,"06-ld r,r.gb":1'
BASE_EMU=41.1; BASE_APP=30.9

mk() { # name emu_fps app_fps challenge renders roms_extra
    cat > "$TMP/$1.json" <<EOF
{"artifact":1,"lint":1,"alive":1,"renders":$5,"challenge":$4,
 "emu_fps":$2,"app_fps":$3,"cpu":75,
 "rom_results":{$ALLPASS$6},
 "trap_diagnostic":1,
 "manifest": $(cat "$TMP/manifest.json"),
 "base_emu":$BASE_EMU,"base_app":$BASE_APP,"anchor":"default"}
EOF
}

score() { python3 "$HERE/score.py" "$TMP/$1.json"; }

check() { # name field expected
    got=$(score "$1" | python3 -c "import json,sys; print(json.load(sys.stdin)['$2'])")
    if [ "$got" != "$3" ]; then
        echo "FAIL $1: $2=$got, expected $3" >&2
        exit 1
    fi
    echo "ok   $1: $2=$got"
}

echo "== v1: unchanged baseline (do nothing) =="
mk v1 41.1 30.9 1 1 ""
check v1 score 0.3
check v1 preserve 1
check v1 regressions "[]"
check v1 realtime 0

echo "== v2: honest full speed =="
mk v2 59.7 59.7 1 1 ""
score v2 > "$TMP/v2.out"
check v2 score 0.999
check v2 preserve 1
check v2 overspeed 0

echo "== v3: fix-one-break-one (hello regressed, full speed) — speed must be ZERO =="
mk v3 59.7 59.7 1 1 ',"hello.gb":0'
check v3 score 0.25
check v3 preserve 0
check v3 regressions "['hello.gb']"
check v3 new_fixes "[]"

echo "== v4: new fix on top of preserved set is counted, not regressed =="
# fixture variant: baseline fails 01-special; submission fixes it, breaks nothing
python3 - "$TMP" <<'EOF'
import glob, json
p = glob.glob('/tmp/gateself.*/manifest.json')[0]
m = json.load(open(p))
m["baseline_passes"] = [r for r in m["baseline_passes"] if r != "01-special.gb"]
json.dump(m, open(p, 'w'))
EOF
mk v4 59.7 59.7 1 1 ""
check v4 preserve 1
check v4 new_fixes "['01-special.gb']"
check v4 score 0.999
# restore full baseline for the remaining cases
python3 - "$TMP" <<'EOF'
import glob, json
p = glob.glob('/tmp/gateself.*/manifest.json')[0]
m = json.load(open(p))
m["baseline_passes"] = m["suite"][:]
json.dump(m, open(p, 'w'))
EOF

echo "== v5: overspeed app (75 fps) — app credit zero, headless capacity kept =="
mk v5 75.0 75.0 1 1 ""
check v5 score 0.5
check v5 overspeed 1
check v5 realtime 0

echo "== v6: no challenge signature — correctness term pays zero =="
mk v6 59.7 59.7 0 1 ""
check v6 score 0.0

echo "== v7: device/ssh dead (empty results) — fail closed =="
cat > "$TMP/v7.json" <<EOF
{"artifact":1,"lint":1,"alive":0,"renders":0,"challenge":0,
 "emu_fps":59.7,"app_fps":59.7,"cpu":0,"rom_results":{},"trap_diagnostic":null,
 "manifest": $(cat "$TMP/manifest.json"),
 "base_emu":$BASE_EMU,"base_app":$BASE_APP,"anchor":"default"}
EOF
check v7 score 0.0
check v7 preserve 0
check v7 regressions "['alu.gb', 'jr.gb', 'intr.gb', 'hello.gb', '01-special.gb', '06-ld r,r.gb']"

echo "== v8: flaky ROM excluded from gate and denominator =="
python3 - "$TMP" <<'EOF'
import glob, json
p = glob.glob('/tmp/gateself.*/manifest.json')[0]
m = json.load(open(p))
m["flaky"] = ["alu.gb"]
m["baseline_passes"] = [r for r in m["baseline_passes"] if r != "alu.gb"]
json.dump(m, open(p, 'w'))
EOF
mk v8 59.7 59.7 1 1 ',"alu.gb":0'
check v8 preserve 1
check v8 score 0.999
python3 - "$TMP" <<'EOF'
import glob, json
p = glob.glob('/tmp/gateself.*/manifest.json')[0]
m = json.load(open(p))
m["flaky"] = []
m["baseline_passes"] = m["suite"][:]
json.dump(m, open(p, 'w'))
EOF

echo "== v9: still_renders fails — no speed credit even fully correct =="
mk v9 59.7 59.7 1 0 ""
check v9 score 0.3

echo "ALL GREEN"
