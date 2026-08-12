#!/usr/bin/env python3
"""Calibration harness for Task 02: score deliberate partial solutions.

Every entry is a named behavioral scenario; the expected outcome is the
design contract. If any scenario deviates, the harness exits 1 — the bands
are part of the frozen rubric, not decoration.

GROUNDWORK STATUS: scenarios and bands are TBD until the reference
implementation and hidden suite exist (see README "Finishing the task").
The harness itself is complete: it builds base/gold trees from the task
directory and runs the same bun junit + score.py pipeline the verifier uses.

Planned scenarios (bands to be fixed by calibration, mirroring Task 01):
  base              0/100    no-op patch earns nothing
  minimal-compose   ~??      composition moved out of intake, host still a
                             dispatcher facade (half the structural work)
  no-shutdown       ~??      gold minus buildBot/shutdown host-owned disposal
  no-cycle          ~??      gold minus the orchestration import-cycle removal
  alt-structure     100/100  correct behavior, different file organization
  gold              100/100  the reference solution
(+ an 'invalid' scenario proving a preservation gate fires)

Usage:
    uv run python calibrate.py \
        [--work /tmp/task02-calibrate] \
        [--node-modules /path/to/node_modules] \
        [--keep]

Needs bun on PATH and a node_modules for little-goblin (default: the
~/build/little-goblin checkout — same lockfile and versions).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
ENV_DIR = TASK_DIR / "environment" / "little-goblin"
REFERENCE_DIR = TASK_DIR / "solution" / "reference"  # TBD until reference lands
HIDDEN_DIR = TASK_DIR / "tests" / "hidden"
SCORE_PY = Path(__file__).parent / "score.py"

EXPECTED = {
    # TODO(groundwork): fill bands once reference + hidden suite exist.
    # "base": ("scored", 0),
    # "gold": ("scored", 100),
}

# The graded file list: every base test file except no-network exclusions.
# Kept in sync with test.sh's EXCLUDE_TESTS.
EXCLUDED_TESTS = {"src/voice.test.ts"}


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, **kw)


def make_tree(work: Path, name: str, src_app: Path | None, node_modules: Path) -> Path:
    d = work / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if src_app is not None:
        shutil.copytree(src_app, d, dirs_exist_ok=True, symlinks=True)
    (d / "node_modules").symlink_to(node_modules, target_is_directory=True)
    return d


def graded_files(d: Path) -> list[str]:
    """Repo-relative test files for the graded run (base suite minus exclusions,
    plus hidden paths — hidden paths land when the hidden suite exists)."""
    files = sorted(str(p.relative_to(d)) for p in d.rglob("*.test.ts"))
    files = [f for f in files if f not in EXCLUDED_TESTS]
    hidden = sorted(str(p.relative_to(d)) for p in HIDDEN_DIR.glob("*.test.ts"))
    files = sorted(set(files) | set(hidden))
    return files


def score(work: Path, name: str, d: Path) -> tuple[str, int | None]:
    junit = work / f"{name}.junit.xml"
    out_dir = work / "out" / name
    r = run(["bun", "test", "--reporter=junit", f"--reporter-outfile={junit}", *graded_files(d)], cwd=d)
    env = dict(os.environ, SCORE_OUT_DIR=str(out_dir))
    s = run(["uv", "run", "python", str(SCORE_PY), str(junit)], cwd=SCORE_PY.parent, env=env)
    reward = json.loads((out_dir / "reward.json").read_text())
    print(f"  {name}: bun_exit={r.returncode} -> {reward['outcome']} score={reward.get('score')}")
    return reward["outcome"], reward.get("score")


def build_scenarios(work: Path, node_modules: Path) -> dict[str, Path]:
    """TODO(groundwork): construct base + gold + partial trees once the
    reference implementation and hidden suite exist. Base tree = ENV_DIR
    (the curated snapshot); gold = base + reference; partials are surgical
    edits of gold targeting the session's "Done means" items."""
    base_app = work / "base-app"
    if base_app.exists():
        shutil.rmtree(base_app)
    base_app.mkdir(parents=True)
    shutil.copytree(ENV_DIR, base_app, dirs_exist_ok=True)
    trees = {"base": make_tree(work, "base", base_app, node_modules)}
    # TBD: gold, alt-structure, partial scenarios
    if REFERENCE_DIR.exists():
        gold_app = work / "gold-app"
        if gold_app.exists():
            shutil.rmtree(gold_app)
        shutil.copytree(base_app, gold_app, symlinks=True)
        for f in REFERENCE_DIR.rglob("*"):
            if f.is_file():
                rel = f.relative_to(REFERENCE_DIR)
                (gold_app / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, gold_app / rel)
        trees["gold"] = make_tree(work, "gold", gold_app, node_modules)
    return trees


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/tmp/task02-calibrate"))
    ap.add_argument("--node-modules", type=Path,
                    default=Path.home() / "build" / "little-goblin" / "node_modules")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if not args.node_modules.exists():
        print(f"node_modules not found at {args.node_modules} — pass --node-modules", file=sys.stderr)
        return 1

    if args.work.exists() and not args.keep:
        shutil.rmtree(args.work)
    args.work.mkdir(parents=True, exist_ok=True)

    trees = build_scenarios(args.work, args.node_modules)
    if not EXPECTED:
        print("GROUNDWORK: EXPECTED bands are not defined yet; nothing to verify. "
              "Add scenarios + bands after the reference implementation and "
              "hidden suite land.", file=sys.stderr)
        return 2

    failures = []
    for name in EXPECTED:
        outcome, score_val = score(args.work, name, trees[name])
        exp_outcome, exp_score = EXPECTED[name]
        ok = outcome == exp_outcome and score_val == exp_score
        if not ok:
            failures.append(f"{name}: got ({outcome}, {score_val}) want ({exp_outcome}, {exp_score})")
            print(f"  !! DEVIATION: {failures[-1]}")

    if failures:
        print("\ncalibration FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("\ncalibration OK: all bands hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())