#!/bin/bash
# Reference solve: apply the verified patch that makes model-thinking the sole owner.
# Patch = curated base (7f00c6a + provider-balance fixture fix) -> 8e1081d bundle state.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH="$SCRIPT_DIR/solution.patch"
if [ ! -f "$PATCH" ]; then
  echo "solution.patch not found at $PATCH" >&2
  exit 1
fi
# Apply from repo root (/app)
cd /app
git apply --binary "$PATCH"
echo "solve.sh: applied $(wc -l < "$PATCH") lines"
