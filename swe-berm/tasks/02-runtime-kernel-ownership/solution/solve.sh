#!/bin/bash
# Apply the reference solution.patch to a base tree.
# Usage: bash solve.sh /path/to/base-tree
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$DIR/../environment/little-goblin}"
cd "$TARGET"
if ! git rev-parse --verify base >/dev/null 2>&1; then
  echo "no base tag in $TARGET — init one (git init && git add -A && git commit && git tag base)"
  exit 1
fi
if [ ! -f "$DIR/solution.patch" ]; then
  echo "solution.patch missing"
  exit 1
fi
git apply --binary "$DIR/solution.patch"
echo "applied $DIR/solution.patch to $TARGET"
