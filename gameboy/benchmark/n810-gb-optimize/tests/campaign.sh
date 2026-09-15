#!/bin/bash
# campaign.sh — freeze the Track B baseline suite manifest (measured, not written).
#
# Builds the vendored reference core ON DEVICE (gcc 3.4.4 — the same compiler
# the baseline uses), runs the scored suite N times at scoring parameters
# (frames 1200), and writes tests/baseline_manifest.json:
#   baseline_passes : ROMs at 100% over all runs -> the preservation set
#   flaky           : 0 < rate < 1               -> diagnostics-only
#   rate == 0 on any scored ROM is FATAL (exit 4): a correct core must pass
#   its own suite; 0% means the instrument is broken, mirroring the
#   stream-guard refusal semantics in test.sh.
#
# The manifest is the gate's ground truth. Never hand-edit it; regenerate
# with --force (e.g. after changing suite.tsv or the cap).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ENVD="$HERE/../environment"
N=20
CAP=1200
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1
MANIFEST="$HERE/baseline_manifest.json"
if [ -f "$MANIFEST" ] && [ "$FORCE" = 0 ]; then
    echo "refusing to overwrite $MANIFEST (use --force)" >&2
    exit 2
fi

# device lock — same protocol as the n810-* tools
i=0
until ssh n810 "mkdir /home/user/.bench-lock" 2>/dev/null; do
    i=$((i + 1)); [ $i -gt 120 ] && { echo "device lock timeout" >&2; exit 3; }
    sleep 5
done
trap 'ssh n810 "rmdir /home/user/.bench-lock" 2>/dev/null' EXIT

echo "[campaign] staging suite + reference sources on device"
ssh n810 "rm -rf /home/user/.n810-run/suite; mkdir -p /home/user/.n810-run/suite/roms /home/user/.n810-run/suite/refsrc"
scp -q "$HERE/suite.tsv" "$HERE/suite_run.sh" n810:/home/user/.n810-run/suite/
scp -q "$HERE"/ref/*.c "$HERE"/ref/*.h n810:/home/user/.n810-run/suite/refsrc/
while IFS=$'\t' read -r f m w; do
    case "$f" in ''|\#*) continue ;; esac
    scp -q "$ENVD/roms/$f" "n810:/home/user/.n810-run/suite/roms/"
done < "$HERE/suite.tsv"
scp -q "$ENVD/roms/trap.gb" n810:/home/user/.n810-run/suite/roms/
ssh n810 "chmod +x /home/user/.n810-run/suite/suite_run.sh"

echo "[campaign] building reference core on device (gcc 3.4.4 -O2 -std=c99)"
if ! ssh n810 "cd /home/user/.n810-run/suite/refsrc && gcc -O2 -std=c99 -o ../hl-ref *.c"; then
    echo "[campaign] FATAL: reference core failed to build on device" >&2
    exit 3
fi
# Hash host-side: the device has no sha256sum/md5sum (not even as busybox
# applets). We hash the exact device-built binary we just exercised.
scp -q n810:/home/user/.n810-run/suite/hl-ref /tmp/campaign.hl-ref
HASH=$(sha256sum /tmp/campaign.hl-ref | awk '{print $1}')
echo "[campaign] hl-ref hash: $HASH"

RESULTS=$(mktemp /tmp/campaign.XXXXXX)
for i in $(seq 1 "$N"); do
    echo "[campaign] suite pass $i/$N"
    ssh n810 "cd /home/user/.n810-run/suite && ./suite_run.sh ./hl-ref frames $CAP" >> "$RESULTS"
done

python3 - "$RESULTS" "$HASH" "$N" "$CAP" "$HERE/suite.tsv" "$MANIFEST" <<'PY'
import collections
import datetime
import json
import sys

res_path, hlhash, n, cap, suite_tsv, out_path = sys.argv[1:7]
n = int(n)

suite, meta = [], {}
for line in open(suite_tsv):
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        continue
    f, mode, want = line.split("\t")
    suite.append(f)
    meta[f] = {"mode": mode, "want": want}

per = collections.defaultdict(list)
diag = []
suite_set = set(suite)
for line in open(res_path):
    line = line.strip()
    if not line:
        continue
    if line.startswith("#diag"):
        diag.append(line.split()[-1] == "1")
        continue
    name, _, val = line.rpartition(" ")   # filenames may contain spaces
    if not name or val not in ("0", "1"):
        sys.exit(f"FATAL: bad result line: {line!r}")
    if name in suite_set:
        per[name].append(val == "1")
    elif name == "trap.gb":      # THE diagnostic (see suite.tsv header)
        diag.append(val == "1")

for f in suite:
    if len(per[f]) != n:
        sys.exit(f"FATAL: {f}: {len(per[f])} results, expected {n} — truncated campaign")

zero = [f for f in suite if not any(per[f])]
if zero:
    sys.exit("FATAL: rate==0 on %s — a correct core must pass its own suite; "
             "instrument broken (want-string wrong, cap too small, or build bad)" % zero)

manifest = {
    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "runs": n,
    "frame_cap": cap,
    "hl_bin": "tests/ref core built on device: gcc 3.4.4 -O2 -std=c99",
    "hl_hash": hlhash,
    "suite": suite,
    "diagnostics": ["trap.gb"],
    "baseline_passes": [f for f in suite if all(per[f])],
    "flaky": [f for f in suite if not all(per[f])],
    "per_rom": {
        **{f: {**meta[f], "rate": round(sum(per[f]) / len(per[f]), 3)} for f in suite},
        "trap.gb": {"mode": "diagnostic", "want": "silent+clean-exit",
                    "rate": round(sum(diag) / len(diag), 3) if diag else None},    },
}
json.dump(manifest, open(out_path, "w"), indent=1)
print(json.dumps({k: manifest[k] for k in ("baseline_passes", "flaky")}, indent=1))
print("trap.gb diagnostic rate:", manifest["per_rom"]["trap.gb"]["rate"])
PY
echo "[campaign] manifest written: $MANIFEST"
