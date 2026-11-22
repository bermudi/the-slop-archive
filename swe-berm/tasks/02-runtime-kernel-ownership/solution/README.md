# solution/ — reference implementation

This directory holds the reference implementation for
02-runtime-kernel-ownership. It is **held out** — never shipped into the
agent's environment, never used at grading time. It exists so reviewers can
verify the task is solvable, the verifier accepts a correct answer, and
calibration runs have a known-100% artifact.

**Reference:** `little-goblin` @
`1c8420b4a50d1f1fd6df90f4147ff3e962fba8e9`, relative to base
`1340493861848583e29aa0b734ba120de09b77dd`.

This is the real implementation of the 2026-08-09 "dependency map panning"
session's exact runtime-kernel cut, not a benchmark-authored stand-in. It was
built and repeatedly reviewed in the 2026-08-12/13 implementation sessions;
the final pre-commit report recorded a clean typecheck and 2,530 passing
tests. Commit `1c8420b` contains the implementation and its review fixes in
one bounded commit. Its immediate successor, `aa3803a`, begins the separate
`PreparedRuntimeAssembler` capability that this task explicitly excludes.

- `solution.patch` — exact binary-safe `git diff` from base to reference.
- `reference/` — the 24 files changed by the reference, for calibration and
  review.
- `solve.sh` — applies `solution.patch` to a base tree.

## solve.sh

Usage: `bash solve.sh /path/to/base-tree` — applies `solution.patch` to a
clean base checkout (the same tree the environment Dockerfile produces).
