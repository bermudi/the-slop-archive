#!/bin/bash
# Verifier for 01-pi-thinking-ownership
# Runs in a SEPARATE container (verifier.environment_mode = "separate") with
# a pristine copy of the base. The agent's patch is collected via
# [[verifier.collect]] into /logs/artifacts/model.patch and applied here.
#
# Grading is deterministic and manifest-driven:
#   - operational outcomes (no_patch / apply_failed / build_failed) are tagged
#     here and never count as capability zeros;
#   - score.py maps the bun junit ledger to the frozen 100-point manifest
#     (tests/points.json). Every point belongs to a named behavioral test that
#     fails on the base state. Missing/duplicate/skipped capability tests,
#     or an unparseable junit, are verifier_error — score.py never falls back
#     to process exit codes, so a crashed run can never look like a pass.
set -uo pipefail
trap 'if [ ! -f /logs/verifier/reward.json ] && [ ! -f /logs/verifier/reward.txt ]; then mkdir -p /logs/verifier; echo "{\"reward\":0,\"outcome\":\"verifier_error\",\"reason\":\"test.sh trapped\"}" > /logs/verifier/reward.json; echo 0 > /logs/verifier/reward.txt; fi' EXIT

log() { echo "[verifier] $*"; }
mkdir -p /logs/verifier
export RUN_LOG=/logs/verifier/run.log
: > "$RUN_LOG" 2>/dev/null || true
run_log() { echo "+ $*" >> "$RUN_LOG" 2>/dev/null; "$@" 2>&1 | tee -a "$RUN_LOG"; return "${PIPESTATUS[0]}"; }

cd /app || { log "no /app"; echo '{"reward":0,"outcome":"verifier_error","reason":"no_app"}' > /logs/verifier/reward.json; echo 0 > /logs/verifier/reward.txt; exit 0; }

# --- 1. Operational outcomes: patch handling ---
PATCH="/logs/artifacts/model.patch"
if [ ! -f "$PATCH" ]; then
  log "no patch artifact at $PATCH -> no_patch"
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"no_patch","reason":"no patch collected from agent"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi
if [ ! -s "$PATCH" ]; then
  log "empty patch -> no_patch"
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"no_patch","reason":"empty patch"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi

log "applying patch $(wc -c < "$PATCH") bytes"
if ! git apply --binary "$PATCH" 2>>"$RUN_LOG"; then
  log "patch apply failed"
  cat /logs/verifier/run.log 2>/dev/null | tail -50
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"apply_failed","reason":"git apply failed"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi
log "patch applied"

# --- 2. Build check ---
# The bundle has no build step beyond bun install (already at image build).
# Verify tsc if a compiler happens to be available. We call it directly (never
# via npx): npx would attempt a network install in a no-network container and
# could hang or spuriously fail. In the stock oven/bun image there is no tsc,
# so this gate is dormant unless the environment ships one.
if command -v tsc >/dev/null 2>&1; then
  log "running tsc --noEmit"
  if ! run_log tsc --noEmit --project pi-packages/bermudis-pi-goodies/tsconfig.json; then
    log "tsc failed -> build_failed"
    cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"build_failed","reason":"tsc failed"}
JSON
    echo 0 > /logs/verifier/reward.txt
    cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
    exit 0
  fi
fi

# --- 3. Inject hidden tests ---
# Replace base test files with the held-out updated suite (behavioral
# verification). The agent's own test files (if they edited them) are
# overwritten with the reference, so their test IDs are exactly the manifest's.
log "injecting hidden tests"
cp /tests/hidden/fixed-defaults.test.ts /app/pi-packages/bermudis-pi-goodies/fixed-defaults.test.ts
cp /tests/hidden/model-thinking.test.ts /app/pi-packages/bermudis-pi-goodies/model-thinking.test.ts
cp /tests/hidden/model-policy.test.ts /app/pi-packages/bermudis-pi-goodies/model-policy.test.ts
cp /tests/hidden/readme-check.test.ts /app/pi-packages/bermudis-pi-goodies/readme-check.test.ts

# --- 4. Run tests with per-test reporting ---
# bun's junit reporter produces XML; score.py converts it to CTRF + reward.
# provider-balance.test.ts is included: its cache test uses a fixture key that
# cannot collide with a real provider, so it is deterministic (the wall-clock
# sin from the old base was fixed in the curated base).
log "running bun test (hidden + adversarial + regression)"
cd /app/pi-packages/bermudis-pi-goodies

set +e
run_log bun test --reporter=junit --reporter-outfile=/tmp/junit.xml \
  fixed-defaults.test.ts model-thinking.test.ts model-policy.test.ts readme-check.test.ts \
  kilo.test.ts prefer-tools.test.ts tps.test.ts provider-balance.test.ts
BUN_EXIT=$?
set -e
log "bun exit $BUN_EXIT"

# --- 5. Score from the ledger (manifest-driven; no exit-code fallback) ---
python3 /tests/score.py /tmp/junit.xml || {
  # score.py already wrote a specific verifier_error reward; only fall back
  # if it couldn't. Never fall back to the bun exit code.
  if [ ! -f /logs/verifier/reward.json ]; then
    log "score.py failed without writing a reward, writing verifier_error"
    cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"verifier_error","reason":"score.py crashed"}
JSON
    echo 0 > /logs/verifier/reward.txt
  fi
}

# --- 6. Surface raw output ---
for f in "$RUN_LOG" /tmp/junit.xml; do
  [ -f "$f" ] && [ -s "$f" ] || continue
  echo "===== $f ====="
  cat "$f" 2>/dev/null | tail -100
done

log "reward.json=$(cat /logs/verifier/reward.json 2>/dev/null)"
# Move junit to reports/ for provenance, keep canonical artifacts at top level
mkdir -p /logs/verifier/reports 2>/dev/null
[ -f /tmp/junit.xml ] && cp /tmp/junit.xml /logs/verifier/reports/junit.xml 2>/dev/null || true
# Clean up injected readme-check (not part of solution)
rm -f /app/pi-packages/bermudis-pi-goodies/readme-check.test.ts
