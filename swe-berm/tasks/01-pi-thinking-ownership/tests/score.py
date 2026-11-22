#!/usr/bin/env python3
"""Score Task 01 from bun's junit.xml against the points manifest.

The manifest (points.json) is the frozen scoring contract: every graded
requirement maps to named behavioral tests with fixed points. No LLM or human
judge is involved at grading time; the same manifest plus the gold junit are
the calibration record.

Outcomes:
  verifier_error — the test ledger cannot be trusted: junit unparseable,
                   duplicate, missing, skipped, or unexpected capability
                   tests. Never awards points.
  invalid        — a preservation or regression test failed or went missing.
                   The solution broke existing behavior; no capability score is
                   awarded, but score_if_valid records the capability points
                   that the otherwise trustworthy ledger earned.
  scored         — every test ran; score = sum of points for passed point
                   tests (0..100). Operational outcomes (no_patch /
                   apply_failed / build_failed) are emitted by test.sh before
                   this script runs and never reach a capability score.

Extra tests in regression files (e.g. an agent adding its own tests) are
ignored; they can't earn points.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MANIFEST = Path(__file__).parent / "points.json"
HIDDEN_FILES = {
    "fixed-defaults.test.ts",
    "model-thinking.test.ts",
    "model-policy.test.ts",
    "bundle-registration.test.ts",
    "readme-check.test.ts",
}
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
        {
            "reward": 0,
            "outcome": "verifier_error",
            "reason": reason,
            "score_if_valid": None,
            "manifest_version": manifest["version"],
        },
        ctrf,
    )
    print(f"[score] verifier_error: {reason}")


def capability_report(manifest: dict, results: dict[str, str]) -> tuple[int, dict[str, int], list[dict]]:
    """Return the capability score and its per-test ledger.

    This is deliberately separate from the preservation/regression gate. A
    failed gate makes a run invalid, but the capability result is still useful
    diagnostic telemetry once the capability ledger itself has passed its
    integrity checks.
    """
    points = manifest["points"]
    score = 0
    cat_scores = {cat: 0 for cat in manifest["categories"]}
    ledger = []
    for key, meta in sorted(points.items()):
        passed = results.get(key) == "passed"
        earned = meta["points"] if passed else 0
        score += earned
        cat_scores[meta["category"]] += earned
        ledger.append(
            {
                "id": key,
                "tier": "hidden" if key.split("::", 1)[0] != "readme-check.test.ts" else "documentation",
                "category": meta["category"],
                "points": meta["points"],
                "earned": earned,
                "status": "passed" if passed else results.get(key, "missing"),
            }
        )

    for key in sorted(set(manifest["preservation"]) | set(manifest["regression"])):
        ledger.append(
            {
                "id": key,
                "tier": "regression",
                "points": 0,
                "earned": 0,
                "status": results.get(key, "missing"),
            }
        )
    return score, cat_scores, ledger


def ctrf_report(results: dict[str, str], ledger: list[dict]) -> dict:
    return {
        "results": {
            "summary": {
                "total": len(results),
                "passed": sum(1 for value in results.values() if value == "passed"),
                "failed": sum(1 for value in results.values() if value != "passed"),
            },
            "tests": ledger,
        }
    }


def main() -> int:
    junit_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/junit.xml")
    manifest = json.loads(MANIFEST.read_text())

    try:
        root = ET.parse(junit_path).getroot()
    except Exception as exc:  # noqa: BLE001 - report and bail, never guess
        fail(manifest, f"junit unparseable: {exc}")
        return 1

    results: dict[str, str] = {}  # test id -> passed|failed|skipped
    dupes: list[str] = []
    for case in root.iter("testcase"):
        key = f"{case.get('file', '?')}::{case.get('name', '?')}"
        if key in results:
            dupes.append(key)
        if case.find("skipped") is not None:
            results[key] = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            results[key] = "failed"
        else:
            results[key] = "passed"

    points = manifest["points"]
    preservation = set(manifest["preservation"])
    regression = set(manifest["regression"])
    capability_keys = set(points) | preservation
    expected_tests = capability_keys | regression

    # --- Ledger integrity for capability tests and skipped gate tests ---
    # Missing capability/preservation tests make the capability ledger
    # untrustworthy. A missing regression test remains an invalid preservation
    # gate below, matching the outcome taxonomy.
    missing_cap = sorted(capability_keys - set(results))
    skipped_expected = sorted(
        key for key in expected_tests if results.get(key) == "skipped"
    )
    unexpected_hidden = sorted(
        k for k in results
        if k not in capability_keys and k.split("::", 1)[0] in HIDDEN_FILES
    )
    if dupes or missing_cap or skipped_expected or unexpected_hidden:
        reason = (
            f"ledger integrity: dupes={dupes} missing={missing_cap} "
            f"skipped={skipped_expected} unexpected_hidden={unexpected_hidden}"
        )
        fail(manifest, reason)
        return 1

    # The capability ledger is trustworthy from here onward. Calculate it
    # before checking the zero-point gates so an invalid run can retain its
    # diagnostic capability score without changing its reward.
    score, cat_scores, ledger = capability_report(manifest, results)

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
                "score_if_valid": score,
                "manifest_version": manifest["version"],
            },
            ctrf_report(results, ledger),
        )
        print(f"[score] invalid: {reason} score_if_valid={score}")
        return 0

    # --- Capability score ---

    reward = {
        "reward": round(score / 100.0, 4),
        "outcome": "scored",
        "score": score,
        "score_if_valid": None,
        "total_points": manifest["total_points"],
        "categories": {
            cat: {"label": manifest["categories"][cat]["label"], "earned": cat_scores[cat], "total": manifest["categories"][cat]["points"]}
            for cat in manifest["categories"]
        },
        "manifest_version": manifest["version"],
    }
    ctrf = ctrf_report(results, ledger)
    write_reports(reward, ctrf)
    print(f"[score] {score}/100 scored (outcome=scored) categories={cat_scores}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
