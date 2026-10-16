#!/bin/bash
# Oracle solution: validates the task is solvable.
# Uses the known-good approach discovered during evaluation:
# native gcc build on device (no v6K poison), SDL 1.2 at 16bpp (managed
# window, not fbdev), headless serial mode for test ROMs.
#
# This builds a minimal DMG emulator core. It's intentionally plain —
# it exists to prove the harness works, not to win the benchmark.
set -e
echo "oracle: see solve reference notes — minimal SDL1.2 GB emulator"
echo "placeholder: copy a known-good source tree here when validating"
