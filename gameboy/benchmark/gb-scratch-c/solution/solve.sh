#!/bin/bash
# Oracle: build the vendored reference core behind the required CLI.
# Validates the task end-to-end (headless serial, frame-out, SDL2 window).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p /work/dist
gcc -O2 -o /work/dist/gbemu gbemu.c ref/*.c -Iref $(sdl2-config --cflags --libs 2>/dev/null || echo -lSDL2)
echo "oracle: built /work/dist/gbemu"
