#!/bin/sh
# suite_run.sh — device-side correctness-suite runner (v3).
#
# Grades each ROM by name with mode-aware semantics, so the scorer and the
# manifest campaign exercise the exact same predicate:
#   blargg mode : pass iff want-substring appears in output AND exit code 0.
#   trap.gb     : diagnostic — correct behavior is silence + clean exit.
#
# Usage (on device, from the dir holding suite.tsv and roms/):
#   ./suite_run.sh <binary> frames|seconds <N>
#     frames  -> "$BIN" roms/<rom> --frames N        (Track B binaries)
#     seconds -> "$BIN" --headless roms/<rom> --seconds N   (Track A binaries)
# Emits one "<file> <1|0>" line per scored ROM, then "#diag trap.gb <1|0>".
set -u
BIN=${1:?binary}; KMODE=${2:-frames}; KARG=${3:-1200}
[ -x "$BIN" ] || { echo "suite_run: $BIN not executable" >&2; exit 2; }

run_one() {
    # $1 = rom file, $2 = want substring ("" = expect silence)
    case "$KMODE" in
        frames)  OUT=$("$BIN" "roms/$1" --frames "$KARG" 2>&1); EC=$? ;;
        seconds) OUT=$("$BIN" --headless "roms/$1" --seconds "$KARG" 2>&1); EC=$? ;;
        *) echo "suite_run: unknown mode $KMODE" >&2; exit 2 ;;
    esac
    if [ "$EC" -ne 0 ]; then echo "$1 0"; return; fi
    if [ -n "$2" ]; then
        printf '%s' "$OUT" | grep -qF -- "$2" && echo "$1 1" || echo "$1 0"
    else
        [ -z "$OUT" ] && echo "$1 1" || echo "$1 0"
    fi
}

while IFS='	' read -r F MODE WANT; do
    [ -n "${F:-}" ] || continue
    case "$F" in \#*) continue ;; esac
    [ "$MODE" = "blargg" ] || { echo "suite_run: unknown mode '$MODE' for $F" >&2; exit 2; }
    run_one "$F" "$WANT"
done < suite.tsv

# diagnostic: trap.gb must run silent and exit cleanly at the cap
run_one trap.gb ""
