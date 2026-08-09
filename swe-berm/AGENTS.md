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

- `main` — the live benchmark: task recipes + docs. Task 01 is scaffolded.
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

**Task 01 — scaffolded: `tasks/01-pi-thinking-ownership/`**
"Single-ownership refactor of a pi extension bundle." Derived from the
2026-08-09 pi session where `bermudis-pi-goodies` had two modules owning
thinking level (`fixed-defaults` + `model-thinking`); the approved fix
(after "lgtm" at event index 62) gave `model-thinking` sole ownership.

- Session transcript:
  `~/.pi/agent/sessions/--home-daniel-build-agent-extensions--/2026-08-09T06-23-37-607Z_019fe530-f087-73d9-b337-f6fe69ab1fa6.jsonl`
- Codebase: `~/build/agent-extensions` — `HEAD` (`7f00c6a`) = base state
  (buggy dual ownership); uncommitted working tree = reference solution
  (7 files: `fixed-defaults.ts`, `fixed-defaults.test.ts`,
  `model-thinking.ts`, `model-thinking.test.ts`, `model-policy.test.ts`
  (new), `README.md`, `index.ts`)
- Proven verdict: 97/98 pass; the 1 failure is a pre-existing
  wall-clock-dependent cache-TTL test in `provider-balance.ts` (reads
  `~/.pi/agent/cache/provider-balance.json`) — the canonical determinism
  sin, excluded from the verifier.

Anatomy (per TASK-DESIGN.md):

- `environment/Dockerfile` — `oven/bun:1.2.21`, bundle at `7f00c6a` with
  `bun install --frozen-lockfile` at build time, `git init` + `tag base`,
  `network_mode = "no-network"`
- `instruction.md` — symptom (sessions start on wrong model/thinking) +
  constraints (single ownership, legacy field ignored, README migration,
  keep suite green); no file-level todo list
- `tests/` — verifier in **separate** environment, per-test CTRF + reward,
  operational outcomes (`no_patch`/`apply_failed`/`build_failed`) apart
  from capability zeros; hidden = updated behavior suite,
  adversarial = `model-policy.test.ts` cross-module integration +
  malformed-config handling, regression = `kilo`, `prefer-tools`, `tps`
  (provider-balance excluded)
- `solution/` — `solution.patch` (1055 lines, 7 files) + `reference/`
  snapshot for reviewers; `solve.sh` applies the patch

Validated: hidden suite fails on base (5/12 fixed-defaults tests fail) and
passes on the reference solution (23/23 hidden+adversarial, 44/44
regression, 69/69 total with README check). No prose gold in the sandbox
(base `grep` for fix keywords is clean).
