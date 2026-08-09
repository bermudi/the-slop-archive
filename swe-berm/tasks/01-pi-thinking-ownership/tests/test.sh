#!/bin/bash
# Verifier for 01-pi-thinking-ownership
# Runs in a SEPARATE container (verifier.environment_mode = "separate") with
# a pristine copy of the base. The agent's patch is collected via
# [[verifier.collect]] into /logs/artifacts/model.patch and applied here.
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
# The bundle has no build step beyond bun install (already at image build)
# Verify tsc if available (type safety)
if command -v tsc >/dev/null 2>&1; then
  log "running tsc --noEmit"
  if ! run_log npx tsc --noEmit --project pi-packages/bermudis-pi-goodies/tsconfig.json; then
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
# Replace base test files with the held-out updated suite (behavioral verification)
# The agent's own test files (if they edited them) are overwritten with the reference.
log "injecting hidden tests"
cp /tests/hidden/fixed-defaults.test.ts /app/pi-packages/bermudis-pi-goodies/fixed-defaults.test.ts
cp /tests/hidden/model-thinking.test.ts /app/pi-packages/bermudis-pi-goodies/model-thinking.test.ts
cp /tests/hidden/model-policy.test.ts /app/pi-packages/bermudis-pi-goodies/model-policy.test.ts

# Also inject a small README check as a hidden test (prose verification)
# We do this as a test file so it appears in the per-test ledger
cat > /app/pi-packages/bermudis-pi-goodies/readme-check.test.ts <<'EOF'
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
describe("README documents single-ownership", () => {
  test("does not describe thinking pinning as part of fixed-defaults", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    // Base README says "pins the current model and thinking level" — must be gone
    expect(readme).not.toContain("pins the current model and thinking level");
    expect(readme).toContain("pins only the cross-session provider and model");
    expect(readme).toContain("model-thinking` is the sole owner");
  });
  test("documents the new provider/model-only JSON shape", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    expect(readme).toContain('"provider":');
    expect(readme).toContain('"model":');
    // Old JSON used defaultProvider/defaultModel/defaultThinkingLevel
    expect(readme).not.toContain("defaultThinkingLevel");
  });
});
EOF

# --- 4. Run tests with per-test reporting ---
# Bun's junit reporter produces XML; we convert to CTRF-ish JSON for Harbor
log "running bun test (hidden + adversarial + regression)"
cd /app/pi-packages/bermudis-pi-goodies

# We run the full suite minus the flaky provider-balance.test.ts (host-state read)
# That test is the determinism-sin example — excluded from the verifier per AGENTS.md
set +e
run_log bun test --reporter=junit --reporter-outfile=/tmp/junit.xml \
  fixed-defaults.test.ts model-thinking.test.ts model-policy.test.ts readme-check.test.ts kilo.test.ts prefer-tools.test.ts tps.test.ts
BUN_EXIT=$?
set -e
log "bun exit $BUN_EXIT"

# --- 5. Convert junit.xml -> ctrf.json + reward.json ---
python3 /tests/parse_junit.py /tmp/junit.xml $BUN_EXIT || {
  log "parse_junit failed, falling back to exit-code reward"
  mkdir -p /logs/verifier
  if [ $BUN_EXIT -eq 0 ]; then
    echo '{"reward":1,"outcome":"pass"}' > /logs/verifier/reward.json
    echo 1 > /logs/verifier/reward.txt
  else
    echo '{"reward":0,"outcome":"fail","reason":"bun tests failed"}' > /logs/verifier/reward.json
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
# Harbor expects ctrf.json at /logs/verifier/ctrf.json (already written by parse_junit)
# and reward.json + run.log as canonical. test-stdout.txt is harness-captured stdout.

# Clean up injected readme-check (not part of solution)
rm -f /app/pi-packages/bermudis-pi-goodies/readme-check.test.ts
