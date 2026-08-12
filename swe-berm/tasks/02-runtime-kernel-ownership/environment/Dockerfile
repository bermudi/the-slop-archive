FROM oven/bun:1.3.7

# 1.3.7 (NOT 1.2.21): little-goblin's base suite uses `vi.useFakeTimers`,
# which bun 1.2.x does not support — on 1.2.21 the coalesce tests double-run
# and fail (24 runs/12 tests, `vi.useFakeTimers is not a function`); the
# final 1.2.23 still fails 8/12 fake-timer tests. 1.3.7's junit ledger is
# key-identical to the reference canary ledger (2503/2503 file::line::name
# keys, 0 failures, 0 dupes) and was validated as the verifier basis.

# System deps for git operations. python3 is required by the verifier's
# manifest scorer (tests/score.py) — Harbor builds the verifier from this
# same image, so it must be present here.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates python3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Curated base: the committed little-goblin tree @ 1340493 ONLY. The
# 2026-08-09 planning session's uncommitted doc edits (ARCHITECTURE.md /
# BACKLOG.md plan records, README.md row, comparison.html) are deliberately
# absent — they spell out the accepted runtime-kernel cycle and would leak
# the task's answer in prose. Context is the environment/ directory (Harbor
# sets CONTEXT_DIR=environment).
COPY little-goblin ./

# Install deps at build time (network allowed during build; the graded run
# is no-network). bun.lock is tracked at HEAD, so --frozen-lockfile is exact.
RUN bun install --frozen-lockfile 2>&1 | tail -20

# Back to repo root and turn it into a git repo at base (no future history
# exists in this snapshot by construction)
WORKDIR /app
RUN git config --global --add safe.directory /app \
 && git init \
 && git config user.email "task@harbor.local" \
 && git config user.name "harbor" \
 && git config core.hooksPath /dev/null \
 && git add . \
 && git commit -m "base: little-goblin @ 1340493 (runtime-kernel ownership base)" \
 && git tag base \
 && git branch -M main

# Sanity: show the base is the pre-refactor state — Telegram intake is the
# composition root with the guarded circular dispatcher hookup.
RUN grep -q "dispatcherRef" src/tg/intake.ts && echo "base: intake is composition root (pre-refactor)" || (echo "base snapshot wrong: dispatcherRef missing from intake"; exit 1)

CMD ["/bin/bash"]