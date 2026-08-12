# Task 02 — runtime-kernel-ownership

Make Conversation runtime ownership physically true in `little-goblin`: a
concrete `ConversationRuntimeHost` owns the Surface-backed ephemeral runtime
state, composition happens before Telegram intake exists, the orchestration
import cycle is removed, and `buildBot` stops exposing mutable runner maps.

The design authority is [`TASK-DESIGN.md`](../../TASK-DESIGN.md); this file
is the task-specific runbook — layout, provenance, grading contract, and how
to **finish** the task.

## Layout

```
environment/
  Dockerfile          base sandbox image (oven/bun 1.2.21, deps baked in)
  little-goblin/      curated base snapshot @ 1340493 (what the agent sees)
instruction.md        the agent prompt (symptom + contract, no grading talk)
tests/
  test.sh             verifier entry point (patch, typecheck gate, restore,
                      hidden injection, run, score)
  score.py            manifest scorer (junit -> reward/ctrf; ledger integrity)
  points.json         THE frozen 100-point rubric (generated; PENDING stub)
  gen_manifest.py     regenerates points.json from gold+base junit runs
  calibrate.py        scores deliberate partial solutions (bands TBD)
  hidden/             held-out contract tests (NOT yet authored; README.md
                      inside fixes the authoring rules)
solution/             reference implementation (PENDING; README.md inside)
task.toml             Harbor recipe config + provenance metadata
```

## Provenance

- **Base** = the *committed* `little-goblin` tree @ `1340493` only.
  1340493's full SHA: `1340493861848583e29aa0b734ba120de09b77dd`.
- **Source session** (the accepted design):
  `~/.pi/agent/sessions/--home-daniel-build-little-goblin--/2026-08-09T03-06-20-626Z_019fe47c-5252-7265-8976-88e31b990d22.jsonl`
  ("dependency map panning", 89 events). It ended at event 84 with the
  bounded "runtime-kernel ownership" cut and the sentence *"This is
  sufficiently bounded to begin implementation once you accept this exact
  cut."* — the cut was never accepted/implemented in-session. The session's
  uncommitted doc edits (ARCHITECTURE.md/BACKLOG.md plan records, README row,
  `comparison.html`) are **excluded from the base**: they spell out the
  accepted cycle, i.e. the task's gold prose. Base state is green: 2,517
  tests pass, and two identical junit ledgers confirm the suite's
  determinism on this host.
- **Reference solution** = **TBD.** Deliberately not authored yet (see
  `solution/README.md`): the reference must be the real, review-proven
  implementation once it exists, not a fabricated stand-in.
- Machine-readable record: `task.toml [metadata]`
  (`base_commit`, `base_curation`, `solution_commit`, `session`).

## Grading contract (once the manifest is generated)

`points.json` maps **named tests to 100 points** across the session's
"Done means" categories (composition, runtime host, lifecycle boundary,
deployment, internal runtime, architecture tier). Every point test must fail
on the curated base and pass on the reference (hard-checked by
`gen_manifest.py`). Regression = the repo's own deterministic suite (all
base test files minus no-network exclusions, ~2,480 tests) plus
preservation tests inside the hidden files — 0 points, but any failure
→ `invalid`.

**Outcome taxonomy** (per run, in `reward.json`):

| Outcome | Meaning |
|---|---|
| `no_patch` / `apply_failed` / `build_failed` | operational: the run never produced a gradeable solution (`build_failed` here = `bun run typecheck` fails — tsc is a repo devDependency) |
| `verifier_error` | the test ledger is untrustworthy (missing/duplicate/unexpected tests, unparseable junit) — never awards points |
| `invalid` | preservation/regression tests failed or went missing; existing behavior broke — no capability score |
| `scored` | everything ran; `score` = 0..100 (also as `reward` 0..1) |

Anti-gaming (same mechanisms as Task 01): the verifier restores **every**
base test file from the `base` tag before grading (weaken/delete attacks
neutralized), deletes any smuggled `bunfig.toml`, runs only the graded file
list (agent-added files can't earn points), and the collector combines
committed + staged + working-tree changes.

## No-network audit (findings so far)

- `src/voice.test.ts` calls the **live edge-tts service** via `uvx` — cannot
  run in a no-network container. Excluded from the graded file list
  (`test.sh` EXCLUDE_TESTS, `gen_manifest.py` EXCLUDED_TESTS,
  `calibrate.py` EXCLUDED_TESTS — keep all three in sync). The instruction
  tells the agent how to self-verify with it excluded.
- Spawn-based tests are safe (`cat`/`sleep`, test doubles, local `bun`).
- No bare `fetch(`/network calls in any other test file; no wall-clock; the
  two-run ledger comparison on the base is identical.
- **Host dry-runs must live on ext4 (`/home`), never `/tmp` (tmpfs).**
  Verified 2026-08-12 on both bun 1.2.21 (the image) and the host canary:
  on tmpfs, `mock.module` from `src/subagents/mod.test.ts` leaks into
  other test processes and breaks `src/agent/contract.test.ts` (7 tests,
  `modelRuntime.registerProvider is not a function`); on ext4 and on the
  container overlay at `/app` the same suite is green (2517/2517).
  Docker sandboxes are unaffected; only host-side verification needs the
  ext4 rule.
- **Open:** a final in-container audit (run the graded list inside the
  built image without network and diff against the host ledger) may surface
  more exclusions. Until that smoke test runs, EXCLUDE_TESTS is provisional.

## Finishing the task (when the real patch exists)

1. **Land the reference implementation** — the review-complete
   runtime-kernel ownership cycle (or whatever the accepted final patch is).
   Copy its source into `solution/reference/`; generate
   `solution/solution.patch` from a scratch repo (`git diff --binary
   base..solution`) and re-point `solution_commit` in `task.toml`.
2. **Author the hidden suite** (`tests/hidden/`) *with* the reference,
   per `tests/hidden/README.md`: one test per session "Done means" item,
   failing on base, passing on reference. Record graded paths in `test.sh`
   (HIDDEN_TARGETS) and `gen_manifest.py` (HIDDEN_FILES).
3. **Write the WEIGHTS map** in `gen_manifest.py` (the calibration decision)
   so points sum to 100 across the six categories.
4. **Produce gold + base junits** (dry-run below) with **bun 1.3.7 — the
   image pin — not the host canary** (the manifest is derived from the
   exact graded runtime) and regenerate `points.json`.
5. **Fill `calibrate.py` EXPECTED bands** with deliberate partials
   (minimal composition, gold minus shutdown, gold minus cycle, alternative
   structure, gold) and confirm they land in designed bands.
6. **Run the validation train**: reverse check (enforced by
   `gen_manifest.py`), one adversarial attempt, alternative-structure
   solution, 3× determinism on base and gold.
7. **Docker smoke** (below) and the in-container no-network audit. The
   smoke must confirm, in the pinned 1.3.7 image: (a) the graded ledger
   matches the host 1.3.7 ledger (0 dupes, 0 failures, 2503 base keys),
   (b) injected hidden tests keep the ledger clean (no mock.module
   leakage), (c) EXCLUDE_TESTS is final.
8. Update this README (grading contract table, hidden-suite composition,
   calibration record) and the SWE-berm AGENTS.md.

## Operating the task

### Dry-run without Docker (ext4 only — see the tmpfs hazard above)

```bash
# 1. base app tree — put it on /home, NOT /tmp (mock.module breaks on tmpfs)
mkdir -p ~/build/t02-dry/app && cp -R tasks/02-runtime-kernel-ownership/environment/little-goblin/* ~/build/t02-dry/app/
ln -s ~/build/little-goblin/node_modules ~/build/t02-dry/app/node_modules
cd ~/build/t02-dry/app && git init -q && git add -A && git commit -qm base && git tag base
# 2. apply the patch under test
git apply --binary <patch>            # or: bash tasks/02-runtime-kernel-ownership/solution/solve.sh ~/build/t02-dry/app
# 3. (verifier does this, but reproduce it) restore base tests + inject hidden
git checkout base -- $(git ls-tree -r --name-only base | grep -E '\.test\.ts$')
cp tasks/02-runtime-kernel-ownership/tests/hidden/*.test.ts ~/build/t02-dry/app/<graded paths>
# 4. typecheck + run the graded list + score
cd ~/build/t02-dry/app && bun run typecheck
bun test --reporter=junit --reporter-outfile=~/build/t02-dry/junit.xml \
  $(git ls-tree -r --name-only base | grep -E '\.test\.ts$' | grep -v '^src/voice\.test\.ts$')
SCORE_OUT_DIR=~/build/t02-dry/out uv run python tasks/02-runtime-kernel-ownership/tests/score.py ~/build/t02-dry/junit.xml
```

`calibrate.py` automates this once scenarios are defined.

**e2e validation (2026-08-12):** the complete verifier pipeline was
simulated on ext4 with bun 1.3.7 (the image pin): collector (committed +
staged + worktree diff, 3 files → 846B patch) → apply → `bun run
typecheck` → base restore → graded run (2503 tests, 0 fail, 0 dupes,
29s) → `score.py` → `reward.json` = `scored 0` with the stub manifest.
This is the deterministic outcome to expect from a base-with-trivial-patch
trial until the manifest is generated.

### Regenerate the manifest

```bash
uv run python tests/gen_manifest.py \
  --gold-junit /tmp/gold-junit.xml \   # graded list vs reference, all green
  --base-junit /tmp/base-junit.xml \   # graded list vs curated base
  --out tests/points.json
```

The generator hard-checks the reverse-classical property (weighted test must
pass on gold **and fail on base**), the 100-point sum, and the excluded-test
list. It currently refuses to emit an empty free-points manifest — expected
until hidden files + weights exist.

### Re-run calibration

```bash
uv run python tests/calibrate.py        # needs bun + little-goblin's node_modules
```

### Docker smoke test (outstanding — dockerd was unavailable)

- [ ] `harbor check tasks/02-runtime-kernel-ownership` (image builds, config valid)
- [ ] base trial (no patch) → expect `scored` 0 (empty manifest) or `no_patch`
- [ ] in-container no-network audit: run the graded file list in the image,
      diff against the host ledger → finalize EXCLUDE_TESTS everywhere
- [ ] one gold trial → expect `scored` 100, all tests in ledger
- [ ] one partial trial → expected band
- [ ] inspect `reward.json`, `ctrf.json`, `run.log` in verifier artifacts
- [ ] gold trial 3× → identical scores

## Known limitations

- **Groundwork state:** the manifest is a zero-point stub, `solution/` is
  empty, `tests/hidden/` is a spec — this task must not be graded until the
  "Finishing the task" checklist runs. It *can* be smoke-tested: the whole
  pipeline (collect → typecheck → restore → run → score) is wired and will
  produce a deterministic 0.
- **bun version pin: `oven/bun:1.3.7` (NOT 1.2.x).** little-goblin's base
  suite uses `vi.useFakeTimers`, which bun ≤1.2.23 cannot run: on the
  original 1.2.21 pin the coalesce tests double-run and fail
  (`vi.useFakeTimers is not a function`; 24 runs for 12 tests — the junit
  also duplicates every other testcase), and the final 1.2.23 still fails
  8/12 of them. Host dry-runs use the canary 1.3.14; the verified
  `env-sim` reference is bun 1.3.7, whose graded ledger (2503
  file::line::name keys) exactly matches the canary's — 0 failures, 0
  dupes. Keep the image pin in `environment/Dockerfile` and confirm it
  with the in-container audit before finalizing.
- **Junit ledger keys:** bun reports 2,517 tests; the junit ledger is keyed
  `file::line::name` (2,517 unique keys — verified; `file::name` collides
  on parametrized tests). The manifest is keyed to the junit (the graded
  ledger), so generation and scoring must run on the same junit.
- **Patch collector** does not capture untracked files; the instruction says
  to commit, so an agent that never `git add`s a new file loses it.
- The "architecture tier" (import-graph assertions) is deliberately
  structural; keep it small and explicit (see `tests/hidden/README.md`).