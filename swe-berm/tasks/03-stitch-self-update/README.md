# Task 03 — stitch-self-update

Add a safe release-binary self-update command to Stitch. This task is
intentionally in **groundwork** state: the real production implementation
does not exist, so there is no reference patch, hidden suite, weighted
manifest, or calibration record yet.

`TASK-DESIGN.md` is authoritative. In particular: no fabricated gold, no live
network, one capability, behavior-only grading, and a separate verifier.

## Why this task

Stitch already publishes versioned Linux archives and SHA-256 sidecars for
`x86_64` and `aarch64`, but installation and updates are manual. Self-update
is one coherent boundary crossing: untrusted remote release data becomes the
currently executing local binary. The engineering work is in version policy,
artifact selection, hostile-input validation, crash-safe replacement,
concurrency, and an honest CLI interface—not in adding another subcommand.

## Provenance and curation

- **Source:** `/home/daniel/build/stitch`
- **Base:** annotated release `v0.14.2`, commit
  `8a78284811abbaa0215a31a2912277276726e115`
- **Curated base adjustment:** the release commit bumped `Cargo.toml` to
  0.14.2 but left the root package entry in `Cargo.lock` at 0.14.1. Running
  Cargo refreshes exactly that one line. The environment folds the 0.14.2
  lock entry into the base so `--locked` verification starts green.
- **Host dirty state:** only that generated lockfile correction existed when
  the task was created; no host source changes were included.
- **Reference:** pending. Do not grade this task until the real Stitch patch
  is complete, reviewed, and materialized under `solution/`.

The environment is a snapshot, not a clone: there is no future Git history
and no gold prose. Existing release documentation remains because artifact
names and supported platforms are part of Stitch's public contract.

## Layout

```
instruction.md          agent-visible capability contract
task.toml               Harbor recipe; no-network + separate verifier
environment/
  Dockerfile            Rust 1.97, base deps, Python scorer, qemu aarch64
  stitch/               curated v0.14.2 source snapshot
  update-deps/          pinned optional crates cached for offline agents
tests/
  test.sh               patch/build/restore/run/score pipeline
  score.py              named-libtest manifest scorer
  gen_manifest.py       reverse-checked manifest generator
  calibrate.py          pending calibration harness
  points.json           zero-point authoring stub
  hidden/README.md      held-out suite authoring contract
solution/
  README.md             why gold is pending + completion steps
  solve.sh              refuses clearly until solution.patch exists
```

## Intended verifier

The held-out integration target runs the CLI against a deterministic loopback
GitHub-compatible repository API selected with `STITCH_UPDATE_BASE_URL`.
`<base>/releases/latest` returns controlled metadata whose asset URLs also
point to loopback. The suite builds valid and hostile release archives in a
temporary directory and updates disposable copies of the executable—never
`/app/stitch` itself. No request may leave the verifier.

The public integration suite (`tests/cli.rs`, 495 tests at the curated base)
is restored from the `base` tag before every run. Inline unit tests cannot be
restored independently of production Rust files, so they are build/lint
inputs but not preservation-ledger gates. The verifier removes agent-added
test targets, restores the public suite, injects its fixed hidden target, then
runs targets explicitly with one test thread.

Native x86_64 tests cover the full flow. The aarch64 selection path must be
run as an aarch64 build under qemu, not inferred from source layout or a
production-only fake-platform flag.

`score.py` parses Cargo/libtest's named default output into
`target::test-name` keys. Missing, duplicated, skipped, or unexpected hidden
tests are `verifier_error`; preservation/regression failure is `invalid`
with diagnostic `score_if_valid`; operational failures remain
`no_patch`/`apply_failed`/`build_failed`.

## Offline dependencies

The sandbox cannot fetch crates. The image caches exact versions of `ureq`,
`tar`, `flate2`, and `semver` via `environment/update-deps/Cargo.lock`.
They are options, not required architecture. An agent may add a needed cached
crate with Cargo offline; no dependency is added to Stitch's base manifest.

## Finishing checklist

1. Implement and review self-update in the source repository.
2. Identify the exact final commit/range. Exclude unrelated release or
   follow-on work; curate only if necessary and record why.
3. Produce `solution/solution.patch` and `solution/reference/`; verify patch
   application against the shipped base.
4. Author `tests/self_update_contract.rs` with the reference and fill hidden
   injection in `test.sh`.
5. Implement the qemu aarch64 run and merge its named ledger with the native
   ledger without duplicate keys.
6. Fill `WEIGHTS`, category totals, and hidden targets in
   `gen_manifest.py`; generate gold/base logs and `points.json`. Every point
   test must pass on gold and fail on base.
7. Add preservation cases and freeze all 495 base integration keys as
   regression gates.
8. Build one structurally different correct implementation and require 100.
9. Calibrate realistic partials: discovery-only, unchecked archive,
   non-atomic replacement, no concurrency fence, incomplete JSON/errors.
10. Adversarially test weakened/deleted tests, extra test targets, build
    config changes, fake ledgers, hanging local servers, and oversized
    responses.
11. Run formatter, clippy, full tests, the complete verifier, and Docker/Harbor
    smoke tests. Gold must score identically three times.
12. Update this README and root `AGENTS.md` with final counts and calibration.

## Current validation

- Curated source: **850 tests pass** (355 unit + 495 CLI integration).
- `cargo fmt --check`: pass.
- `cargo clippy --locked --all-targets --all-features -- -D warnings`: pass.
- Docker/Harbor: pending; dockerd is unavailable on the authoring host.
- Groundwork scorer: expected to report `scored 0` from the restored 495-test
  CLI ledger until the manifest is authored.

## Dry-run groundwork without Docker

Use a disposable ext4 directory:

```bash
cp -a environment/stitch /home/$USER/build/t03-dry
cd /home/$USER/build/t03-dry
git init && git add -A && git commit -m base && git tag base
# apply a non-empty patch under test
cargo fmt --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked --test cli -- --test-threads=1 \
  > /tmp/t03-cargo-test.log 2>&1
SCORE_OUT_DIR=/tmp/t03-score \
  uv run python ../SWE-berm/tasks/03-stitch-self-update/tests/score.py \
  /tmp/t03-cargo-test.log
```
