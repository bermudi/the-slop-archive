#!/bin/bash
# Oracle for n810-gb-optimize: proves the task is solvable.
# The baseline builds unmodified via `make arm` / `make arm-headless` on
# device — staging the unmodified build must produce a valid, lint-clean,
# correctness-passing artifact at baseline speed (~0.2-0.3x realtime).
set -e
n810-build /work/baseline arm
n810-build /work/baseline arm-headless
scp -q n810:~/bench/baseline/gbn810-arm /work/dist/gbn810-arm
scp -q n810:~/bench/baseline/gbn8-arm-headless /work/dist/gbn8-arm-headless
chmod +x /work/dist/*
