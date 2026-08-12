# AGENTS.md

## Project

A **personal benchmark** for comparing frontier LLMs as agents **through pi**,
built on [Harbor](https://github.com/harbor-framework/harbor) task recipes.
No paper, no public leaderboard — the output is a private ranking of
model+thinking configs on tasks derived from real engineering work.

The old benchmark (clean-room systems-programming tasks + a hand-rolled
Python harness) is dead. It lives on the `legacy` branch if anything needs
looking up. Do not resurrect it.

## Layout

- `main` — the live benchmark: task recipes + docs. Task 01 is final.
- `legacy` — the old stack at `42a2b54` (Python harness, old Task 01 DNS
  codec, archived agent sessions). Read-only museum.
- `TASK-DESIGN.md` — **the authority on how tasks are designed**: Harbor
  anatomy, red lines, prompt/verifier/environment rules, failure-mode
  taxonomy, and §10's relaxation guide (what a personal benchmark skips).
  Any task that contradicts it is wrong by definition.
- `tasks/` — Harbor task recipes:
  - `tasks/01-pi-thinking-ownership/` — single-ownership refactor of
    `bermudis-pi-goodies` (see Current state).

## Stack & tooling

- **Harbor** (`harbor` CLI, installed via `uv tool install harbor`) runs
  trials: agent in a Docker sandbox, verifier in a separate environment,
  per-test structured results. Reference: harborframework.com/docs and the
  cookbook repo. DeepSWE's repo (`github.com/datacurve-ai/deep-swe`) is the
  reference implementation of the recipe pattern; **Pier** (their Harbor
  fork) exists for air-gapped tasks with per-agent network allowlists —
  consider it if Harbor's no-network blocks the pi agent's LLM calls.
- **The pi agent adapter does not exist yet.** Harbor's `BaseAgent`
  subclass is the plan: pi in RPC mode inside the environment, model swaps
  via Harbor's model connection layer (replaces the old hand-rolled
  models.json provider pinning).
- Design sources: DeepSWE v1/v1.1 blog posts, FrontierCode post (saved
  copies in ~/Downloads, cited in TASK-DESIGN.md).

## Red lines (carry over, enforced by Harbor config)

- **Determinism.** No wall-clock, no live network, no host state in graded
  paths. `network_mode = "no-network"` on every task.
- **Behavioral verification.** Verifiers test observable behavior through
  public interfaces; never internal symbols or structure.
- **No gold in the sandbox** — including prose. Grep the base state for
  the fix's keywords (AGENTS.md, TODOs, changelogs leak intent).
- **Separate verifier environment** + per-test structured report, with
  operational outcomes (`no_patch`/`apply_failed`/`build_failed`) tagged
  apart from capability zeros.
- **One capability per task.** No dependency chains.

Full rationale and the failure stories behind each: TASK-DESIGN.md.

## Current state

**Task 01 — final: `tasks/01-pi-thinking-ownership/`**
"Single-ownership refactor of a pi extension bundle." Derived from the
2026-08-09 pi session where `bermudis-pi-goodies` had two modules owning
thinking level (`fixed-defaults` + `model-thinking`); the approved fix
(after "lgtm" at event index 62) gave `model-thinking` sole ownership.

The final implementation is `agent-extensions` @ `48ac5c5` — which is a
*stack* of four commits (`f0972bb` split, `aea4772` provider-balance test
fix, `8e1081d` review hardening, `48ac5c5` reset/failed-load fixes).
**The benchmark base is curated, not a single commit**: bundle @ `7f00c6a`
+ the unrelated `provider-balance.test.ts` fixture-key fix from `aea4772`,
folded INTO the base so the graded patch is exactly one capability (9 files)
and the base suite is fully green. See `task.toml` `[metadata]` for
provenance.

- Session transcript:
  `~/.pi/agent/sessions/--home-daniel-build-agent-extensions--/2026-08-09T06-23-37-607Z_019fe530-f087-73d9-b337-f6fe69ab1fa6.jsonl`
- Source codebase: `~/build/agent-extensions` (bundle history is public
  there; only the curated snapshot ships in the task).

Anatomy (per TASK-DESIGN.md):

- `README.md` — the task runbook: layout, grading contract, outcome
  taxonomy, hidden-suite composition (reference vs. rubric-added), how to
  dry-run, regenerate the manifest (`tests/gen_manifest.py`), re-run
  calibration (`tests/calibrate.py`), add a graded point, and the
  outstanding Docker smoke-test checklist.
- `environment/Dockerfile` — `oven/bun:1.2.21`, curated base snapshot with
  `bun install --frozen-lockfile` at build time, `git init` + `tag base`,
  python3 installed (the verifier's scorer needs it), `network_mode =
  "no-network"`
- `instruction.md` — symptom + constraints; states every graded
  requirement (single ownership, legacy field ignored + warn once,
  status/migration behavior, reset semantics, README migration, green suite)
- `tests/` — verifier in **separate** environment, deterministic
  **manifest scoring**: `points.json` (frozen 100-point rubric, every point
  on a base-failing behavioral test) + `score.py` (ledger integrity:
  missing/duplicate/skipped/unexpected tests → `verifier_error`, never a
  pass; no exit-code fallback). Regeneration and calibration are committed
  tooling: `gen_manifest.py` (gold/base junit → points.json, hard-checks
  the reverse check) and `calibrate.py` (scores 11 deliberate partials,
  bands are a contract). Operational outcomes
  (`no_patch`/`apply_failed`/`build_failed`) stay apart from capability
  scores; preservation/regression failures → `invalid` (reward 0, with
  diagnostic `score_if_valid`).
  Hidden = 16 fixed-defaults + 12 model-thinking + 3 model-policy + 1
  bundle-registration + 4 readme-check; regression = kilo, prefer-tools,
  tps, **provider-balance (now hermetic** — fixture cache key)
- `solution/` — `solution.patch` (1617 lines, 9 files incl. new
  `json-file.ts`, `model-policy.test.ts`, `bundle-registration.test.ts`) +
  `reference/` snapshot @ `48ac5c5`; `solve.sh` applies the patch

Validated (dry-run in /tmp, no Docker):

- Base (curated) scores **0/100**; reference scores **100/100** —
  reproduced across multiple dry-runs and in every calibration run.
- Calibration record (manifest v3, reference @ `48ac5c5`): listener-only
  fix = 5 (bundle-level evidence), minimal ownership split = 47,
  gold−reset-persist = 89, gold−legacy-warning = 95, gold−docs = 92,
  gold−failed-load-retry = 96, pre-`48ac5c5` reset on invalid files =
  `invalid` (the two reset preservation gates fail), alternative structure
  (no shared json-file.ts) = 100, disabled fixed-defaults = `invalid`
  (preservation gate). Manifest v2 (reference @ `8e1081d`) bands were
  5/47/87/94/92/100/invalid; the `48ac5c5` rebalance moved
  gold−reset-persist to 89 and gold−legacy-warning to 95. The
  `48ac5c5` reset-on-invalid and legacy-only tests are zero-point
  preservation gates because they also pass on the curated base (base
  reset never touches settings); weighting them would break base ≠ 0.
  Their active model was hardened to a non-default pair
  (`anthropic/claude-sonnet-4`) so they detect the pre-fix clobber — the
  upstream originals passed a model equal to the fixture's saved defaults,
  which made the settings-unchanged assertion vacuous. The
  bundle-registration test exercises the REAL entry point (index.ts), so
  a patch that breaks or unregisters the modules can't score 100. Regression-suite attacks are neutralized: the
  verifier restores kilo/prefer-tools/tps/provider-balance tests from the
  `base` tag before running (weaken-attack → build/invalid, delete-attack
  → neutralized); a smuggled `bunfig.toml` is deleted before the run;
  patch collection stages the final non-ignored worktree and emits one
  coherent base-to-final diff (new files do not need a manual `git add`).
- No prose gold in the sandbox (base `grep` for fix keywords is clean).
- Docker daemon was unavailable during this pass — `harbor run` still
  needs a final smoke test once dockerd is up.
