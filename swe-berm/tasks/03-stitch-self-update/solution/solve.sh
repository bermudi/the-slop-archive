#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$DIR/../environment/stitch}"
if [ ! -f "$DIR/solution.patch" ]; then
  echo "solution.patch missing — the real Stitch self-update implementation does not exist yet" >&2
  exit 1
fi
cd "$TARGET"
git apply --binary "$DIR/solution.patch"
