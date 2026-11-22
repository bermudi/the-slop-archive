#!/usr/bin/env python3
"""Score Task 02 from bun's junit.xml against the points manifest.

The manifest (points.json) is the frozen scoring contract: every graded
requirement maps to named behavioral tests with fixed points. No LLM or human
judge is involved at grading time; the same manifest plus the gold junit are
the calibration record.

Outcomes:
  verifier_error — the test ledger cannot be trusted: junit unparseable,
                   duplicate capability tests, missing capability tests, or
                   unexpected tests in hidden files. Never awards points.
  invalid        — a preservation or regression test failed or went missing.
                   The solution broke existing behavior; no capability score.
  scored         — every test ran; score = sum of points for passed point
                   tests (0..100). Operational outcomes (no_patch /
                   apply_failed / build_failed) are emitted by test.sh before
                   this script runs and never reach a capability score.

For this task the regression set is the repo's own deterministic suite
(all base test files except the no-network-excluded ones, e.g.
src/voice.test.ts). Hidden files are the held-out contract/architecture
tests; their graded repo-relative paths (e.g. "src/orchestration/
x.contract.test.ts") are listed in the manifest (hidden_files key), so
this script stays generic across hidden-suite edits. bun runs from the
repo root, so junit 'file' attributes are repo-relative paths; entries in
hidden_files must match them exactly.

Skipped tests count as failed. Extra tests in regression files (e.g. an agent
adding its own tests) are ignored; they can't earn points.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MANIFEST = Path(__file__).parent / "points.json"
OUT_DIR = Path(os.environ.get("SCORE_OUT_DIR") or "/logs/verifier")


def write_reports(reward: dict, ctrf: dict) -> None:
    out = OUT_DIR
    try:
        out.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        out = Path("/tmp/verifier")
        out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text(json.dumps(reward, indent=2))
    # reward.txt carries the normalized 0..1 reward (matching the old binary
    # convention); the integer capability score lives in reward.json["score"].
    (out / "reward.txt").write_text(str(reward.get("reward", 0)))
    (out / "ctrf.json").write_text(json.dumps(ctrf, indent=2))


def fail(manifest, reason: str) -> None:
    ctrf = {"results": {"summary": {"total": 0, "passed": 0, "failed": 0}, "tests": []}}
    write_reports(
        {"reward": 0, "outcome": "verifier_error", "reason": reason, "manifest_version": manifest.get("version")},
        ctrf,
    )
    print(f"[score] verifier_error: {reason}")


def main() -> int:
    junit_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/junit.xml")
    manifest = json.loads(MANIFEST.read_text())
    hidden_files = set(manifest.get("hidden_files") or [])

    try:
        root = ET.parse(junit_path).getroot()
    except Exception as exc:  # noqa: BLE001 - report and bail, never guess
        fail(manifest, f"junit unparseable: {exc}")
        return 1

    results: dict[str, str] = {}  # test id -> passed|failed|skipped
    dupes: list[str] = []
    for case in root.iter("testcase"):
        # Key is file::line::name: bun runner junit emits parametrized tests
        # (describe.each / repeated names in different describes) as separate
        # testcase elements sharing file+name but differing in source line.
        # Collapsing them would lose genuine coverage; letting the bare
        # file::name collide would false-positive the ledger-integrity check.
        key = f"{case.get('file', '?')}::{case.get('line', '?')}::{case.get('name', '?')}"
        if key in results:
            dupes.append(key)
        if case.find("skipped") is not None:
            results[key] = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            results[key] = "failed"
        else:
            results[key] = "passed"

    points = manifest.get("points") or {}
    preservation = set(manifest.get("preservation") or [])
    regression = set(manifest.get("regression") or [])
    capability_keys = set(points) | preservation

    # --- Ledger integrity for capability tests ---
    missing_cap = sorted(capability_keys - set(results))
    unexpected_hidden = sorted(
        k for k in results
        if k not in capability_keys and k.split("::", 1)[0] in hidden_files
    )
    if dupes or missing_cap or unexpected_hidden:
        reason = (
            f"ledger integrity: dupes={dupes} missing={missing_cap} "
            f"unexpected_hidden={unexpected_hidden}"
        )
        fail(manifest, reason)
        return 1

    # --- Preservation + regression gates (0 points, must pass) ---
    gate_failures = [
        k for k in (preservation | regression)
        if results.get(k) != "passed"
    ]
    missing_gate = sorted((preservation | regression) - set(results))
    if gate_failures or missing_gate:
        reason = (
            f"regression/preservation failure: failed={sorted(gate_failures)} "
            f"missing={missing_gate}"
        )
        write_reports(
            {
                "reward": 0,
                "outcome": "invalid",
                "reason": reason,
                "score": None,
                "manifest_version": manifest.get("version"),
            },
            {"results": {"summary": {"total": len(results), "passed": 0, "failed": len(gate_failures) + len(missing_gate)}, "tests": []}},
        )
        print(f"[score] invalid: {reason}")
        return 0

    # --- Capability score ---
    score = 0
    cat_scores = {cat: 0 for cat in manifest.get("categories") or {}}
    ledger = []
    categories = manifest.get("categories") or {}
    for key, meta in sorted(points.items()):
        passed = results.get(key) == "passed"
        earned = meta["points"] if passed else 0
        score += earned
        cat_scores[meta["category"]] += earned
        ledger.append(
            {
                "id": key,
                "tier": "hidden",
                "category": meta["category"],
                "points": meta["points"],
                "earned": earned,
                "status": "passed" if passed else results.get(key, "missing"),
            }
        )

    for key in sorted(preservation | regression):
        ledger.append({"id": key, "tier": "regression", "points": 0, "earned": 0, "status": "passed"})

    reward = {
        "reward": round(score / 100.0, 4) if manifest.get("total_points") else 0,
        "outcome": "scored",
        "score": score,
        "total_points": manifest.get("total_points"),
        "categories": {
            cat: {"label": categories[cat]["label"], "earned": cat_scores[cat], "total": categories[cat]["points"]}
            for cat in categories
        },
        "manifest_version": manifest.get("version"),
    }
    ctrf = {
        "results": {
            "summary": {
                "total": len(results),
                "passed": sum(1 for v in results.values() if v == "passed"),
                "failed": sum(1 for v in results.values() if v != "passed"),
            },
            "tests": ledger,
        }
    }
    write_reports(reward, ctrf)
    print(f"[score] {score}/{manifest.get('total_points') or 0} scored (outcome=scored) categories={cat_scores}")
    return 0


if __name__ == "__main__":
    sys.exit(main())