# solution/ — reference implementation (pending)

This directory holds the reference implementation for
02-runtime-kernel-ownership. It is **held out** — never shipped into the
agent's environment, never used at grading time. It exists so reviewers can
verify the task is solvable, the verifier accepts a correct answer, and
calibration runs have a known-100% artifact.

**Status: pending.** Per the 2026-08-09 "dependency map panning" session
(`session` key in `task.toml`), the runtime-kernel ownership cycle was
accepted as the next implementation cycle but was never implemented — the
session ends at the "exact cut" proposal (event 84), and no later session or
commit implements it. This task deliberately does **not** ship a fabricated
reference: the design contract is the session's prose (its "Done means" and
explicit non-goals, mirrored in `instruction.md`), and the reference must be
the real, finished, review-proven implementation once it exists.

When the reference lands, this directory gains:

- `solution.patch` — `git diff --binary base..solution` in a scratch repo
  (curated base -> reference), generated per the task README.
- `reference/` — the reference tree (source files only), for calibration
  and review.
- `solve.sh` — applies `solution.patch` to a base tree (scaffolded below).

## solve.sh

Usage: `bash solve.sh /path/to/base-tree` — applies `solution.patch` to a
clean base checkout (the same tree the environment Dockerfile produces).