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

- `main` — the live benchmark: task recipes + docs. Currently docs only.
- `legacy` — the old stack at `42a2b54` (Python harness, old Task 01 DNS
  codec, archived agent sessions). Read-only museum.
- `TASK-DESIGN.md` — **the authority on how tasks are designed**: Harbor
  anatomy, red lines, prompt/verifier/environment rules, failure-mode
  taxonomy, and §10's relaxation guide (what a personal benchmark skips).
  Any task that contradicts it is wrong by definition.
- `tasks/` — Harbor task recipes (none yet; Task 01 is next — see below).

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

## Current state & next task

**Task 01 (planned, not scaffolded): "single-ownership refactor of a pi
extension bundle."** Derived from a real pi session (2026-08-09) where the
user's `bermudis-pi-goodies` bundle had two modules owning thinking level
(`fixed-defaults` + `model-thinking`); the approved fix gave
`model-thinking` sole ownership. Source material:

- Session transcript:
  `~/.pi/agent/sessions/--home-daniel-build-agent-extensions--/2026-08-09T06-23-37-607Z_019fe530-f087-73d9-b337-f6fe69ab1fa6.jsonl`
  ("lgtm" approval at event index 62; everything after is the fix)
- Codebase: `~/build/agent-extensions` (uncommitted working tree = the
  reference solution; HEAD = base state)
- Proven verdict: 97/98 tests pass; the 1 failure is a pre-existing
  wall-clock-dependent cache-TTL test in `provider-balance.ts` (reads the
  live `~/.pi/agent/cache/provider-balance.json`) — the canonical example
  of the determinism sin, kept as documentation, out of the verifier.

Planned anatomy: environment bakes the bundle at pre-change state with
vendored `node_modules`; instruction states the symptom + constraints (not
the fix); verifier = updated behavior suite (hidden) + cross-module
integration test (adversarial) + untouched suites as regression.
