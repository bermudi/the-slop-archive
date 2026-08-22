#!/bin/bash
# Separate-environment verifier for Task 03. Groundwork is fully wired; hidden
# injection and the 100-point manifest remain empty until the real gold exists.
set -uo pipefail
trap 'if [ ! -f /logs/verifier/reward.json ]; then mkdir -p /logs/verifier; printf "%s\n" "{\"reward\":0,\"outcome\":\"verifier_error\",\"reason\":\"test.sh trapped\"}" > /logs/verifier/reward.json; echo 0 > /logs/verifier/reward.txt; fi' EXIT

mkdir -p /logs/verifier
RUN_LOG=/logs/verifier/run.log
: > "$RUN_LOG"
log() { echo "[verifier] $*" | tee -a "$RUN_LOG"; }
report_operational() {
  local outcome="$1" reason="$2"
  printf '{"reward":0,"outcome":"%s","reason":"%s"}\n' "$outcome" "$reason" > /logs/verifier/reward.json
  echo 0 > /logs/verifier/reward.txt
  echo '{"results":{"summary":{"total":0,"passed":0,"failed":0},"tests":[]}}' > /logs/verifier/ctrf.json
}

cd /app || { report_operational verifier_error no_app; exit 0; }
PATCH=/logs/artifacts/model.patch
if [ ! -s "$PATCH" ]; then
  report_operational no_patch "no non-empty patch"
  exit 0
fi
if ! git apply --binary "$PATCH" >>"$RUN_LOG" 2>&1; then
  report_operational apply_failed "git apply failed"
  exit 0
fi

# Restore the public integration suite and remove any agent-added tests. Inline
# unit tests live with production code and are not used as preservation gates;
# the 495-test public CLI suite is.
git clean -fd -- tests >>"$RUN_LOG" 2>&1 || true
if ! git checkout base -- tests >>"$RUN_LOG" 2>&1; then
  report_operational verifier_error "could not restore base integration tests"
  exit 0
fi

# Authored with the real reference. Basename and Cargo test target are fixed.
HIDDEN_TARGETS=""
for target in $HIDDEN_TARGETS; do
  cp "/tests/hidden/$target.rs" "/app/tests/$target.rs" || {
    report_operational verifier_error "hidden test injection failed"
    exit 0
  }
done

log "format/build/lint gates"
if ! cargo fmt --check >>"$RUN_LOG" 2>&1 \
  || ! cargo check --locked --all-targets >>"$RUN_LOG" 2>&1 \
  || ! cargo clippy --locked --all-targets --all-features -- -D warnings >>"$RUN_LOG" 2>&1; then
  report_operational build_failed "fmt, cargo check, or clippy failed"
  exit 0
fi

args=(--locked --no-fail-fast --test cli)
for target in $HIDDEN_TARGETS; do args+=(--test "$target"); done
log "running native integration ledger"
set +e
cargo test "${args[@]}" -- --test-threads=1 > /tmp/cargo-test.log 2>&1
test_exit=$?
set -e
cat /tmp/cargo-test.log >>"$RUN_LOG"
log "cargo test exit $test_exit"

python3 /tests/score.py /tmp/cargo-test.log || true
if [ ! -f /logs/verifier/reward.json ]; then
  report_operational verifier_error "score.py failed without a report"
fi
mkdir -p /logs/verifier/reports
cp /tmp/cargo-test.log /logs/verifier/reports/cargo-test.log
tail -100 "$RUN_LOG"
log "reward=$(cat /logs/verifier/reward.json)"
