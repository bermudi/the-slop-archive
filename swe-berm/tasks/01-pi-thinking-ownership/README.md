# Task 01 — pi-thinking-ownership

Single-ownership refactor of the `bermudis-pi-goodies` pi extension bundle:
`model-thinking` becomes the sole owner of thinking levels; `fixed-defaults`
pins only the startup provider/model. The design authority is
[`TASK-DESIGN.md`](../../TASK-DESIGN.md) (Harbor anatomy, red lines, failure
taxonomy); this file is the task-specific runbook — layout, grading contract,
and how to operate, extend, and validate the task.

## Layout

```
environment/    base sandbox image + curated bundle snapshot (what the agent sees)
instruction.md  the agent prompt (symptom + constraints, no grading talk)
tests/
  test.sh         verifier entry point (patch handling, hidden injection, run)
  score.py        manifest scorer (junit -> reward/ctrf; ledger integrity)
  points.json     THE frozen 100-point rubric (generated, do not hand-edit)
  gen_manifest.py regenerates points.json from gold+base junit runs
  calibrate.py    scores deliberate partial solutions; bands are a contract
  hidden/         held-out test files (injected over the agent's copies)
solution/
  solution.patch  the graded patch (curated base -> reference)
  reference/      the reference solution state (review only, never graded)
  solve.sh        applies solution.patch to a base tree
task.toml         Harbor recipe config + provenance metadata
```

## Provenance

- **Curated base** = `agent-extensions` bundle @ `7f00c6a` plus the
  `provider-balance.test.ts` fixture-key fix from `aea4772` folded **in**.
  The fix is unrelated to the task; folding it in makes the base suite fully
  green and the graded patch exactly one capability.
- **Reference solution** = the bundle @ `48ac5c5` (the approved
  post-review implementation **plus** the 2026-08-11 fix commit on top): 9
  files, including new `json-file.ts`, `model-policy.test.ts`,
  `bundle-registration.test.ts`. The reference is a *stack* of four commits
  (`f0972bb` split, `aea4772` provider-balance test fix folded into the
  base, `8e1081d` review hardening, `48ac5c5` reset/failed-load fixes); the
  graded patch is their combined delta from the curated base.
- Machine-readable record: `task.toml [metadata]`
  (`base_commit`, `base_curation`, `solution_commit`).

## Grading contract

`points.json` maps **19 named behavioral tests to 100 points** across 7
categories. Every point test fails on the curated base and passes on the
reference — a no-op patch scores 0 by construction. No LLM or human judge is
involved at grading time.

Manifest history: v2 graded the reference @ `8e1081d` (18 tests). The
`48ac5c5` bump shipped v3: the repaired-config retry became a weighted point
(`malformed_config`), and the two reset-on-inactive-file tests joined the
preservation gate — they pass on the curated base too (base reset never
touches settings), so weighting them would hand free points to a no-op.
They fail on the pre-`48ac5c5` reset semantics, so reverting the fix now
scores `invalid`.

| Category | Points | What it grades |
|---|---|---|
| ownership_split | 32 | fixed-defaults stops owning thinking (set/events/status/legacy) |
| legacy_migration | 11 | one-time legacy warning; `set` rewrites legacy files |
| malformed_config | 20 | broken JSON and invalid shapes reported, never overwritten; repaired configs are retried, not cached |
| reset | 14 | persist-active-model-before-delete (valid pins); no-model refusal; policy preserved |
| integration | 10 | legacy pin cannot override thinking, current + next session |
| bundle_registration | 5 | the real `index.ts` entry point registers correctly |
| documentation | 8 | README: no thinking claim, new JSON shape, migration, fresh-session timing |

**Outcome taxonomy** (per run, in `reward.json`):

| Outcome | Meaning |
|---|---|
| `no_patch` / `apply_failed` / `build_failed` | operational: the run never produced a gradeable solution |
| `verifier_error` | the test ledger is untrustworthy (missing/duplicate/skipped/unexpected tests, unparseable junit) — never awards points or a diagnostic score |
| `invalid` | preservation/regression tests failed; existing behavior broke — `reward` stays 0, while `score_if_valid` records the diagnostic capability score |
| `scored` | everything ran; `score` = 0..100 (also as `reward` 0..1) |

Preservation tests (17) and the regression suites (kilo, prefer-tools, tps,
provider-balance — 79 tests) award 0 points but gate the run: any failure →
`invalid`. Anti-gaming: the verifier restores regression test files from the
`base` tag (weaken/delete attacks are neutralized), deletes any smuggled
`bunfig.toml`, and the collector stages the final non-ignored worktree before
emitting one base-to-final patch.

## Hidden suite composition

Which tests ship with the reference (`48ac5c5`) vs. which the rubric added:

| File | Tests | Origin |
|---|---|---|
| `fixed-defaults.test.ts` | 16 | 14 reference + 2 added: legacy warning emitted **once**; `set` rewrites a legacy file |
| `model-thinking.test.ts` | 12 | 11 reference + 1 added: `set` refuses a config with an invalid thinking level |
| `model-policy.test.ts` | 3 | all reference (cross-module integration) |
| `bundle-registration.test.ts` | 1 | added — exercises the real entry point via a Proxy harness |
| `readme-check.test.ts` | 4 | verifier-injected; 3 from scaffold (loosened phrasing) + 1 added: fresh-session timing |

The two reset tests from `48ac5c5` (invalid file, legacy-only file) are
preservation gates, not points — see the manifest history note above. Their
active model was hardened to a non-default pair (`anthropic/claude-sonnet-4`)
so they actually detect the pre-fix clobber; the upstream originals passed a
model identical to the fixture's saved defaults, which made the
settings-unchanged assertion vacuous.

The added tests grade prompt-stated requirements that the reference suite did
not pin down; the reference passes them by construction.

## Operating the task

### Dry-run without Docker

The verifier needs `/app`, `/tests`, `/logs` (container paths). On the host,
build the trees and run the same pipeline the verifier runs:

```bash
# 1. curated base app
mkdir -p /tmp/hb/app && cp -R tasks/01-pi-thinking-ownership/environment/pi-packages/bermudis-pi-goodies/* /tmp/hb/app/
ln -s <bundle-node_modules> /tmp/hb/app/node_modules   # e.g. ~/build/agent-extensions/.../node_modules
# 2. apply the agent patch (or the reference patch)
cd /tmp/hb/app && git init -q && git add -A && git commit -qm base && git tag base
git apply --binary tasks/01-pi-thinking-ownership/solution/solution.patch
# 3. inject hidden tests
cp tasks/01-pi-thinking-ownership/tests/hidden/*.ts /tmp/hb/app/
# 4. run + score
cd /tmp/hb/app && bun test --reporter=junit --reporter-outfile=/tmp/junit.xml \
  fixed-defaults.test.ts model-thinking.test.ts model-policy.test.ts \
  bundle-registration.test.ts readme-check.test.ts \
  kilo.test.ts prefer-tools.test.ts tps.test.ts provider-balance.test.ts
SCORE_OUT_DIR=/tmp/score-out uv run python tasks/01-pi-thinking-ownership/tests/score.py /tmp/junit.xml
```

`calibrate.py` automates all of this (builds base/gold trees from the task
directory itself) — prefer it over the manual steps above.

### Regenerate the manifest

```bash
uv run python tests/gen_manifest.py \
  --gold-junit /tmp/gold-junit.xml \   # hidden+regression suites vs reference, all green
  --base-junit /tmp/base-junit.xml \   # same suites vs curated base
  --out tests/points.json
```

The generator hard-checks the reverse-classical property: every weighted test
must pass on gold **and fail on base**, or it exits 1. A compile error or
missing weighted test on base is also rejected rather than being mistaken for
an intentional behavioral failure. Weights live in the generator's `WEIGHTS`
map — that is the calibration decision point.

### Re-run calibration

```bash
uv run python tests/calibrate.py          # needs bun + the bundle's node_modules
```

Scores 11 deliberate scenarios (base, listener-only, minimal split, gold minus
reset-persist / legacy-warning / docs / failed-load-retry, pre-`48ac5c5` reset
on invalid files, disabled module, alternative structure, gold) and exits 1 if
any band deviates from `EXPECTED`. Bands are part of the frozen rubric;
if a change moves a band intentionally, update `EXPECTED` in the same commit as
the change.

### Add a graded point (the full chain)

1. Write the hidden test in `tests/hidden/` — it must **fail on base** and
   **pass on gold** (verify with `calibrate.py` or the dry-run steps).
2. Mirror it into `solution/reference/` (hidden == reference).
3. Add its weight to `gen_manifest.py` `WEIGHTS` (and adjust a `CATEGORIES`
   total so the sum stays 100).
4. Regenerate `points.json` (it will refuse if the reverse check fails).
5. Regenerate `solution/solution.patch`: apply the reference over a base
   tree in a scratch git repo, `git diff --binary base..solution`.
6. Run `calibrate.py`; update `EXPECTED` if the band moved on purpose.
7. Update the calibration record in `AGENTS.md`.

### Docker smoke test (still outstanding)

The task was validated by host dry-runs; dockerd was never available. Before
the first real trial, run:

- [ ] `harbor check tasks/01-pi-thinking-ownership` (image builds, config valid)
- [ ] one gold trial (`solve.sh` path) → expect `scored` 100, 115/115 tests
- [ ] one base trial (no patch) → expect `scored` 0 (capability) or `no_patch`
- [ ] one partial trial (e.g. the minimal split) → expect ~47
- [ ] inspect `reward.json`, `ctrf.json`, `run.log` in the verifier artifacts
- [ ] run the gold trial 3× → identical scores

## Known limitations

- The warn-once test captures global `console.warn`; empirically stable
  across runs, but it is the test most likely to flake if bun changes its
  file-level concurrency model.
- The `tsc` build gate is dormant in the stock image (typescript is not a
  bundle dependency); type-broken patches surface as runtime test failures,
  not `build_failed`.
- The collector stages non-ignored final worktree changes before creating the
  base-to-final patch, so new files do not require an explicit `git add` or
  commit. Gitignored files remain excluded.
- `reward.json`: `reward` is the normalized 0..1 float, `score` the integer
  capability score for a valid run, and invalid runs expose their diagnostic
  capability score as `score_if_valid`; `reward.txt` carries the 0..1 value
  (matches the old binary convention).
