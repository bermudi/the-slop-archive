#!/usr/bin/env python3
"""Generate Task 03's frozen manifest from base and gold libtest logs.

Fill WEIGHTS, CATEGORIES, and HIDDEN_TARGETS only after the real reference and
held-out suite exist. Every weighted test must pass on gold and fail on base.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from score import parse

WEIGHTS: dict[str, tuple[str, int]] = {}
CATEGORIES: dict[str, dict[str, object]] = {
    "discovery": {"label": "release discovery and version policy", "points": 0},
    "selection": {"label": "platform and artifact selection", "points": 0},
    "verification": {"label": "checksum and archive validation", "points": 0},
    "installation": {"label": "atomic installation and concurrency", "points": 0},
    "interface": {"label": "human/JSON/error interface", "points": 0},
}
HIDDEN_TARGETS: set[str] = set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-log", required=True, type=Path)
    parser.add_argument("--base-log", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("points.json"))
    args = parser.parse_args()

    if not WEIGHTS or not HIDDEN_TARGETS:
        print("AUTHORING: reference/hidden suite/weights are not finalized")
        return 2

    gold, gold_dupes = parse(args.gold_log)
    base, base_dupes = parse(args.base_log)
    if gold_dupes or base_dupes:
        raise SystemExit(f"duplicate ledger keys: gold={gold_dupes} base={base_dupes}")

    point_keys: set[str] = set()
    for key in gold:
        target, name = key.split("::", 1)
        if target in HIDDEN_TARGETS and name in WEIGHTS:
            point_keys.add(key)

    problems: list[str] = []
    for key in sorted(point_keys):
        if gold.get(key) != "passed":
            problems.append(f"{key}: gold must pass")
        if base.get(key) == "passed":
            problems.append(f"{key}: base passes (free points)")
        if key not in base:
            problems.append(f"{key}: missing from base ledger")
    weighted_names = {key.split("::", 1)[1] for key in point_keys}
    if weighted_names != set(WEIGHTS):
        problems.append(
            f"weight/test mismatch: tests={sorted(weighted_names)} weights={sorted(WEIGHTS)}"
        )
    if problems:
        raise SystemExit("\n".join(problems))

    points = {
        key: {"category": WEIGHTS[key.split("::", 1)[1]][0], "points": WEIGHTS[key.split("::", 1)[1]][1]}
        for key in point_keys
    }
    if sum(int(meta["points"]) for meta in points.values()) != 100:
        raise SystemExit("weights must sum to 100")

    preservation = sorted(
        key
        for key in gold
        if key.split("::", 1)[0] in HIDDEN_TARGETS and key not in point_keys
    )
    regression = sorted(
        key for key in gold if key.split("::", 1)[0] not in HIDDEN_TARGETS
    )
    manifest = {
        "version": 1,
        "total_points": 100,
        "categories": CATEGORIES,
        "points": points,
        "preservation": preservation,
        "regression": regression,
        "hidden_targets": sorted(HIDDEN_TARGETS),
        "provenance": {
            "generator": "tests/gen_manifest.py",
            "gold_log": str(args.gold_log),
            "base_log": str(args.base_log),
        },
    }
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}: {len(points)} point tests, {len(regression)} regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
