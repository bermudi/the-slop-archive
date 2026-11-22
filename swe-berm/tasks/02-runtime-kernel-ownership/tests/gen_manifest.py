#!/usr/bin/env python3
"""Regenerate tests/points.json from the gold and base junit runs (Task 02).

The manifest is the frozen scoring contract for
02-runtime-kernel-ownership. This generator is the single source of truth
for its derivation; editing points.json by hand is discouraged (regenerate
instead).

Usage:
    uv run python gen_manifest.py \
        --gold-junit /tmp/gold-junit.xml \
        --base-junit /tmp/base-junit.xml \
        [--out tests/points.json]

Inputs:
  --gold-junit  a bun junit of the GRADED FILES (deterministic base suite
                minus no-network exclusions, plus hidden tests) run against
                the REFERENCE solution (every test passes).
  --base-junit  the same graded-file junit run against the CURATED BASE
                (all capability tests fail, preservation/regression pass).

Checks performed (each is a hard error, not a warning):
  * every weighted test appears exactly once in both junits;
  * every weighted test PASSES on gold and FAILS on base (the reverse check —
    a point test that passes on base would hand free points to a no-op);
  * preservation/regression tests are derived from the gold run and are not
    weighted; for this task every base test file in the gold junit is
    regression, and hidden-file tests that are not weighted are preservation;
  * weights sum to 100 and match the category totals;
  * no unexpected files in either junit (hidden basenames are the only
    non-base files allowed, and they must be declared in HIDDEN_FILES).

GROUNDWORK STATUS: WEIGHTS and HIDDEN_FILES are intentionally empty until the
hidden suite is authored against the reference implementation (see
tests/hidden/README.md and the task README "Finishing the task"). The
generator's checks are complete and will refuse a broken manifest.

The weight map below is the calibration decision; it is intentionally frozen.
Planned categories (from the session's "Done means" contract), weights TBD:
  - composition        intake receives lifecycle+dispatcher; no construction
                       inside the adapter; no nullable deferred hookup
  - runtime_host       host owns registration/queues/generation identity/
                       fingerprints/in-flight identity; synchronous
                       invalidation before async cleanup; no resurrection;
                       command-queue preservation
  - lifecycle_boundary host does not import the dispatcher; lifecycle depends
                       on the narrow runtime contract; no orchestration cycle
  - deployment         buildBot exposes no mutable runner maps; shutdown
                       walks host-owned disposal
  - internal_runtime   Surface-free internal runtimes stay separate
  - architecture       import-graph assertions (deliberate structural tier)
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# test name -> (category, points)  — TODO(groundwork): fill when hidden suite exists
WEIGHTS = {}

CATEGORIES = {
    "composition": {"label": "composition leaves the Telegram adapter", "points": 0},
    "runtime_host": {"label": "runtime host owns Surface-backed runtime state", "points": 0},
    "lifecycle_boundary": {"label": "lifecycle/runtime host boundary", "points": 0},
    "deployment": {"label": "buildBot + shutdown via host-owned disposal", "points": 0},
    "internal_runtime": {"label": "Surface-free internal runtimes stay separate", "points": 0},
    "architecture": {"label": "architecture / import-graph assertions", "points": 0},
}

# Hidden tests live in tests/hidden/ and are injected under graded paths
# with NEW names that must not collide with any base test file. Entries are
# the repo-relative graded paths (bun runs from /app; junit 'file'
# attributes are repo-relative), e.g. "src/orchestration/x.contract.test.ts".
# TODO(groundwork): fill when the hidden suite is authored.
HIDDEN_FILES = set()

# Base test files that cannot pass in a no-network container. The graded file
# list mirrors test.sh's EXCLUDE_TESTS; keep the two in sync.
EXCLUDED_TESTS = {"src/voice.test.ts"}


def collect(junit_path: Path) -> dict[str, str]:
    """test id -> 'passed' | 'failed' | 'skipped'.

    Keys are file::line::name — bun's junit emits parametrized tests as
    separate testcase elements sharing file+name but differing in source
    line; the line component keeps each real invocation a distinct ledger
    entry and makes the integrity check meaningful.
    """
    root = ET.parse(junit_path).getroot()
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        key = f"{case.get('file', '?')}::{case.get('line', '?')}::{case.get('name', '?')}"
        assert key not in results, f"duplicate test id in {junit_path}: {key}"
        if case.find("skipped") is not None:
            results[key] = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            results[key] = "failed"
        else:
            results[key] = "passed"
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold-junit", required=True, type=Path)
    ap.add_argument("--base-junit", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "points.json")
    args = ap.parse_args()

    gold = collect(args.gold_junit)
    base = collect(args.base_junit)

    # point keys: hidden-file tests whose name appears in the weight map
    point_keys = set()
    for key in gold:
        f, _line, name = key.split("::", 2)
        if f in HIDDEN_FILES and name in WEIGHTS:
            point_keys.add(key)

    if not WEIGHTS and not HIDDEN_FILES:
        sys.stderr.write(
            "GROUNDWORK: WEIGHTS/HIDDEN_FILES are empty; a manifest can only be "
            "generated once the hidden suite exists. Refusing to write an empty "
            "free-points manifest.\n"
        )
        return 2

    # --- weighted names must be unique per hidden file ---
    # Parametrized repeats (same name at different lines) would double-count
    # weights; hidden tests must therefore use distinct names. This mirrors
    # test.sh's file-list restores: the graded line numbers come from the
    # authored hidden files, so the keys are stable.
    name_counts: dict[str, int] = {}
    for key in gold:
        f, _line, name = key.split("::", 2)
        if f in HIDDEN_FILES and name in WEIGHTS:
            name_counts[name] = name_counts.get(name, 0) + 1
    if any(c > 1 for c in name_counts.values()):
        viol = {n: c for n, c in name_counts.items() if c > 1}
        print(f"weighted hidden test names must be unique per file: {viol}", file=sys.stderr)
        return 1

    # --- reverse check: every point test passes on gold, fails on base ---
    problems = []
    for key in sorted(point_keys):
        g = gold.get(key)
        b = base.get(key)
        if g != "passed":
            problems.append(f"{key}: gold={g} (want passed)")
        if b == "passed":
            problems.append(f"{key}: base={b} (want failed — would award free points to a no-op)")
        if b is None:
            problems.append(f"{key}: missing from base junit")
    if problems:
        print("manifest checks failed:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    # --- derive preservation + regression from gold ---
    preservation = []
    regression = []
    for key in sorted(gold):
        f, _name = key.split("::", 1)
        if f in HIDDEN_FILES:
            if key not in point_keys:
                preservation.append(key)
        elif f in EXCLUDED_TESTS:
            print(f"excluded test present in gold junit: {f} — the graded file "
                  f"list must not run it", file=sys.stderr)
            return 1
        else:
            regression.append(key)
    unknown_files = {k.split("::", 1)[0] for k in base} - set(non_hidden_files(gold)) - HIDDEN_FILES
    if unknown_files:
        print(f"unexpected files in base junit: {sorted(unknown_files)}", file=sys.stderr)
        return 1

    # --- weights sum + category totals ---
    points = {key: {"category": WEIGHTS[key.split("::", 2)[2]][0],
                    "points": WEIGHTS[key.split("::", 2)[2]][1]}
              for key in point_keys}
    total = sum(v["points"] for v in points.values())
    cat_total = {c: 0 for c in CATEGORIES}
    for v in points.values():
        cat_total[v["category"]] += v["points"]
    if total != 100:
        print(f"points sum {total} != 100", file=sys.stderr)
        return 1
    if cat_total != {c: CATEGORIES[c]["points"] for c in CATEGORIES}:
        print(f"category totals mismatch: {cat_total}", file=sys.stderr)
        return 1

    manifest = {
        "version": 1,
        "total_points": 100,
        "provenance": {
            "generator": "tests/gen_manifest.py",
            "gold_junit": str(args.gold_junit),
            "base_junit": str(args.base_junit),
            "excluded_tests": sorted(EXCLUDED_TESTS),
            "note": "Regenerate with gen_manifest.py; do not hand-edit weights.",
        },
        "categories": CATEGORIES,
        "points": points,
        "preservation": sorted(preservation),
        "regression": sorted(regression),
        "hidden_files": sorted(HIDDEN_FILES),
    }
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    print(f"  points: {len(points)} tests / {total} pts")
    print(f"  preservation: {len(preservation)} tests")
    print(f"  regression: {len(regression)} tests")
    for cat, t in cat_total.items():
        print(f"    {cat}: {t} pts")
    return 0


def non_hidden_files(gold: dict[str, str]) -> set[str]:
    """Repo-relative paths of every non-hidden file in the gold junit."""
    return {k.split("::", 1)[0] for k in gold if k.split("::", 1)[0] not in HIDDEN_FILES}


if __name__ == "__main__":
    sys.exit(main())