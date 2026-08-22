#!/usr/bin/env python3
"""Score Stitch's named libtest ledger against the frozen Task 03 manifest."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MANIFEST = Path(__file__).with_name("points.json")
OUT_DIR = Path(os.environ.get("SCORE_OUT_DIR") or "/logs/verifier")

RUNNING = re.compile(r"^\s*Running (?:unittests )?([^ ]+) \(")
CASE = re.compile(r"^test (.+) \.\.\. (ok|FAILED|ignored)$")


def write_reports(reward: dict[str, object], tests: list[dict[str, object]]) -> None:
    out = OUT_DIR
    try:
        out.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        out = Path("/tmp/verifier")
        out.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(tests),
        "passed": sum(t.get("status") == "passed" for t in tests),
        "failed": sum(t.get("status") != "passed" for t in tests),
    }
    (out / "reward.json").write_text(json.dumps(reward, indent=2) + "\n")
    (out / "reward.txt").write_text(str(reward.get("reward", 0)))
    (out / "ctrf.json").write_text(
        json.dumps({"results": {"summary": summary, "tests": tests}}, indent=2) + "\n"
    )


def parse(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return target::test -> status and duplicate keys from cargo test output."""
    current: str | None = None
    results: dict[str, str] = {}
    duplicates: list[str] = []
    for raw in path.read_text(errors="replace").splitlines():
        running = RUNNING.match(raw)
        if running:
            current = running.group(1)
            continue
        case = CASE.match(raw)
        if not case or current is None:
            continue
        key = f"{current}::{case.group(1)}"
        if key in results:
            duplicates.append(key)
        results[key] = {
            "ok": "passed",
            "FAILED": "failed",
            "ignored": "skipped",
        }[case.group(2)]
    return results, duplicates


def verifier_error(manifest: dict[str, object], reason: str) -> int:
    write_reports(
        {
            "reward": 0,
            "outcome": "verifier_error",
            "reason": reason,
            "manifest_version": manifest.get("version"),
        },
        [],
    )
    print(f"[score] verifier_error: {reason}")
    return 1


def main() -> int:
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/cargo-test.log")
    manifest: dict[str, object] = json.loads(MANIFEST.read_text())
    try:
        results, duplicates = parse(log)
    except Exception as exc:  # ledger failure must never become a capability zero
        return verifier_error(manifest, f"could not parse libtest log: {exc}")
    if not results:
        return verifier_error(manifest, "libtest ledger is empty")

    points: dict[str, dict[str, object]] = manifest.get("points") or {}  # type: ignore[assignment]
    preservation = set(manifest.get("preservation") or [])
    regression = set(manifest.get("regression") or [])
    capability = set(points) | preservation
    hidden_targets = set(manifest.get("hidden_targets") or [])

    missing_capability = sorted(capability - set(results))
    unexpected_hidden = sorted(
        key
        for key in results
        if key.split("::", 1)[0] in hidden_targets and key not in capability
    )
    if duplicates or missing_capability or unexpected_hidden:
        return verifier_error(
            manifest,
            "ledger integrity: "
            f"duplicates={duplicates} missing={missing_capability} "
            f"unexpected_hidden={unexpected_hidden}",
        )

    score = sum(
        int(meta["points"])
        for key, meta in points.items()
        if results.get(key) == "passed"
    )
    gate_failures = sorted(
        key for key in preservation | regression if results.get(key) != "passed"
    )

    ledger: list[dict[str, object]] = []
    for key, meta in sorted(points.items()):
        status = results.get(key, "missing")
        earned = int(meta["points"]) if status == "passed" else 0
        ledger.append(
            {
                "id": key,
                "tier": "hidden",
                "category": meta["category"],
                "points": meta["points"],
                "earned": earned,
                "status": status,
            }
        )
    for key in sorted(preservation | regression):
        ledger.append(
            {
                "id": key,
                "tier": "regression",
                "points": 0,
                "earned": 0,
                "status": results.get(key, "missing"),
            }
        )

    if gate_failures:
        write_reports(
            {
                "reward": 0,
                "outcome": "invalid",
                "reason": f"regression/preservation failure: {gate_failures}",
                "score": None,
                "score_if_valid": score,
                "manifest_version": manifest.get("version"),
            },
            ledger,
        )
        print(f"[score] invalid; score_if_valid={score}")
        return 0

    total = int(manifest.get("total_points") or 0)
    categories: dict[str, dict[str, object]] = manifest.get("categories") or {}  # type: ignore[assignment]
    category_scores = {name: 0 for name in categories}
    for key, meta in points.items():
        if results.get(key) == "passed":
            category_scores[str(meta["category"])] += int(meta["points"])
    write_reports(
        {
            "reward": round(score / 100, 4) if total else 0,
            "outcome": "scored",
            "score": score,
            "total_points": total,
            "categories": category_scores,
            "manifest_version": manifest.get("version"),
        },
        ledger,
    )
    print(f"[score] {score}/{total} (outcome=scored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
