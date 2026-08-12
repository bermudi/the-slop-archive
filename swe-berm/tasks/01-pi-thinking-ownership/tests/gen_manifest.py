#!/usr/bin/env python3
"""Regenerate tests/points.json from the gold and base junit runs.

The manifest is the frozen scoring contract for Task 01. This generator is the
single source of truth for its derivation; editing points.json by hand is
discouraged (regenerate instead).

Usage:
    uv run python gen_manifest.py \
        --gold-junit /tmp/gold-junit.xml \
        --base-junit /tmp/base-junit.xml \
        [--out tests/points.json]

Inputs:
  --gold-junit  a bun junit of the hidden+regression suites run against the
                REFERENCE solution (every test passes).
  --base-junit  the same suites run against the CURATED BASE (all capability
                tests fail, preservation/regression pass).

Checks performed (each is a hard error, not a warning):
  * every weighted test appears exactly once in both junits;
  * every weighted test PASSES on gold and FAILS on base (the reverse check —
    a point test that passes on base would hand free points to a no-op);
  * preservation/regression tests are derived from the gold run and are not
    weighted;
  * weights sum to 100 and match the category totals.

The weight map below is the calibration decision; it is intentionally frozen.
The 2026-08-11 reference bump (48ac5c5) rebalanced it: `malformed_config`
gained the repaired-config retry point (4), and `legacy_migration`/`reset`
shed one point each to keep the sum at 100. The new reset-on-invalid-file
tests from that commit are NOT weighted: they pass on the curated base too
(base reset never touches settings), so they would break the reverse check;
they ship as zero-point preservation gates instead.
See the task README for the rationale and calibration record.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# test name -> (category, points)
WEIGHTS = {
    "legacy thinkingLevel is ignored and does not pin thinking": ("ownership_split", 10),
    "model events restore the pinned override without changing thinking": ("ownership_split", 10),
    "set pins the active model and applies it immediately": ("ownership_split", 6),
    "status shows the effective pin, active model, and override path": ("ownership_split", 6),
    "the legacy thinkingLevel warning is emitted once, not on every read": ("legacy_migration", 5),
    "set rewrites a legacy override file into the provider/model-only format": ("legacy_migration", 6),
    "set refuses to overwrite malformed config": ("malformed_config", 5),
    "status reports malformed config instead of treating it as empty": ("malformed_config", 5),
    "set refuses to overwrite a config with an invalid thinking level": ("malformed_config", 6),
    "reset removes the override and stops pinning": ("reset", 7),
    "reset without an active model leaves the pin in place": ("reset", 3),
    "reset removes only the model pin and preserves thinking policy": ("reset", 4),
    "reloads a repaired config even when size and mtime are unchanged": ("malformed_config", 4),
    "a legacy pin cannot override thinking in the current or next fresh session": ("integration", 10),
    "the entry point registers both ownership modules and no thinking listener": ("bundle_registration", 5),
    "fixed-defaults is described as pinning provider/model only": ("documentation", 2),
    "shows the provider/model-only JSON shape": ("documentation", 2),
    "documents the legacy thinkingLevel migration": ("documentation", 2),
    "explains that a hand-created pin applies from the next fresh session": ("documentation", 2),
}

CATEGORIES = {
    "ownership_split": {"label": "fixed-defaults stops owning thinking", "points": 32},
    "legacy_migration": {"label": "legacy thinkingLevel migration & warnings", "points": 11},
    "malformed_config": {"label": "malformed model-thinking config handling", "points": 20},
    "reset": {"label": "reset semantics", "points": 14},
    "integration": {"label": "cross-session integration", "points": 10},
    "bundle_registration": {"label": "bundle entry point registration", "points": 5},
    "documentation": {"label": "documentation", "points": 8},
}

HIDDEN_FILES = {
    "fixed-defaults.test.ts",
    "model-thinking.test.ts",
    "model-policy.test.ts",
    "bundle-registration.test.ts",
    "readme-check.test.ts",
}
REGRESSION_FILES = ["kilo.test.ts", "prefer-tools.test.ts", "tps.test.ts", "provider-balance.test.ts"]


def collect(junit_path: Path) -> dict[str, str]:
    """test id -> 'passed' | 'failed' | 'skipped'"""
    root = ET.parse(junit_path).getroot()
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        key = f"{case.get('file', '?')}::{case.get('name', '?')}"
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
        f, name = key.split("::", 1)
        if f in HIDDEN_FILES and name in WEIGHTS:
            point_keys.add(key)

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
        if f in REGRESSION_FILES:
            regression.append(key)
        elif f in HIDDEN_FILES and key not in point_keys:
            preservation.append(key)
        elif f not in HIDDEN_FILES:
            print(f"unexpected file in gold junit: {f}", file=sys.stderr)
            return 1

    # --- weights sum + category totals ---
    points = {key: {"category": WEIGHTS[key.split("::", 1)[1]][0],
                    "points": WEIGHTS[key.split("::", 1)[1]][1]}
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
        "version": 3,
        "total_points": 100,
        "provenance": {
            "generator": "tests/gen_manifest.py",
            "gold_junit": str(args.gold_junit),
            "base_junit": str(args.base_junit),
            "note": "Regenerate with gen_manifest.py; do not hand-edit weights.",
        },
        "categories": CATEGORIES,
        "points": points,
        "preservation": sorted(preservation),
        "regression": sorted(regression),
    }
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    print(f"  points: {len(points)} tests / {total} pts")
    print(f"  preservation: {len(preservation)} tests")
    print(f"  regression: {len(regression)} tests")
    for cat, t in cat_total.items():
        print(f"    {cat}: {t} pts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
