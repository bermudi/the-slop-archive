#!/bin/bash
# Verifier for 02-runtime-kernel-ownership
# Runs in a SEPARATE container (verifier.environment_mode = "separate") with
# a pristine copy of the base. The agent's patch is collected via
# [[verifier.collect]] into /logs/artifacts/model.patch and applied here.
#
# Grading is deterministic and manifest-driven:
#   - operational outcomes (no_patch / apply_failed / build_failed) are tagged
#     here and never count as capability zeros;
#   - the typecheck gate (bun run typecheck) is the build check — tsc is a
#     repo devDependency, so it runs offline from node_modules;
#   - score.py maps the bun junit ledger to the frozen 100-point manifest
#     (tests/points.json). Every point belongs to a named test that fails on
#     the base state. Missing/duplicate/skipped capability tests, or an
#     unparseable junit, are verifier_error — score.py never falls back to
#     process exit codes, so a crashed run can never look like a pass.
#
# GROUNDWORK STATUS: the hidden suite (HIDDEN_TARGETS) and the finalized
# no-network exclusion list (EXCLUDE_TESTS) land with the reference
# implementation. Everything else is wired and can be smoke-tested with an
# empty manifest.
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

# --- 2. Build check: full strict typecheck ---
# tsc is a devDependency (node_modules/.bin/tsc), so this runs offline.
log "running bun run typecheck"
if ! run_log bun run typecheck; then
  log "typecheck failed -> build_failed"
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"build_failed","reason":"bun run typecheck failed"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi

# --- 3. Restore every base test file, then inject the hidden suite ---
# The agent's patch may have weakened or deleted existing tests; the graded
# contract is the pristine base suite, so all tracked test files come back
# from the base tag first (deletions neutralized: git checkout recreates
# them). Hidden contract tests are then injected under their graded names.
log "restoring base test files"
BASE_TESTS=$(git ls-tree -r --name-only base | grep -E '\.test\.ts$' || true)
if [ -z "$BASE_TESTS" ]; then
  log "no base test files found -> verifier_error"
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"verifier_error","reason":"base tag has no test files"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi
if ! run_log git checkout base -- $BASE_TESTS; then
  log "base restore failed -> verifier_error"
  cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"verifier_error","reason":"could not restore base test files"}
JSON
  echo 0 > /logs/verifier/reward.txt
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
  exit 0
fi

# Hidden contract tests land here when authored (see tests/hidden/README.md).
# Name rule: basenames must not collide with any base test file. Each copy
# targets its graded path under /app/src/.
# TODO(groundwork): HIDDEN_TARGETS="src/orchestration/<name>.test.ts src/..."
#   cp /tests/hidden/<file>.test.ts /app/<graded-path>
HIDDEN_TARGETS=""
for t in $HIDDEN_TARGETS; do
  f=$(basename "$t")
  log "injecting hidden test $f -> $t"
  cp "/tests/hidden/$f" "/app/$t" || {
    log "hidden injection failed -> verifier_error"
    cat > /logs/verifier/reward.json <<'JSON'
{"reward":0,"outcome":"verifier_error","reason":"hidden test injection failed"}
JSON
    echo 0 > /logs/verifier/reward.txt
    cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}
JSON
    exit 0
  }
done

# A patch could smuggle a bunfig.toml that preloads a test monkey-patch (bun
# test auto-loads bunfig). The base has none; remove any the agent added so
# the graded run uses stock bun behavior.
find /app -name bunfig.toml -delete 2>/dev/null || true

# --- 4. Run tests with per-test reporting ---
# Graded files = every base test file EXCEPT the no-network exclusions, plus
# the hidden targets. Exclusions are env-dependent tests that cannot pass in
# a no-network container (e.g. src/voice.test.ts calls the live edge-tts
# service); the list is finalized by the in-container audit (see README).
EXCLUDE_TESTS='^src/voice[.]test[.]ts$'
RUN_FILES=$(printf '%s\n' $BASE_TESTS | grep -vE "$EXCLUDE_TESTS" || true)
for t in $HIDDEN_TARGETS; do RUN_FILES="$RUN_FILES $t"; done
RUN_FILES=$(printf '%s\n' $RUN_FILES | sed '/^$/d' | sort -u)
log "graded files: $(printf '%s\n' "$RUN_FILES" | wc -l)"
cd /app

set +e
# shellcheck disable=SC2086
run_log bun test --reporter=junit --reporter-outfile=/tmp/junit.xml $RUN_FILES
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