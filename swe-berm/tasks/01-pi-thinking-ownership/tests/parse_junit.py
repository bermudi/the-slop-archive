#!/usr/bin/env python3
"""Convert bun junit.xml -> Harbor CTRF + reward.json with tiering and operational outcomes.

Bun's junit reporter produces:
  <testsuites><testsuite><testcase classname="..." name="..."><failure>...</failure></testcase>...

We map each testcase to a CTRF test and compute reward:
  - hidden: fixed-defaults.test.ts, model-thinking.test.ts, README check
  - adversarial: model-policy.test.ts (cross-module integration)
  - regression: kilo, prefer-tools, tps
All hidden+adversarial must pass for reward=1. Regression is included but not
weighted separately here — per TASK-DESIGN, a regression failure still
zeroes the run (real contributions don't get to break the build).
The triage rule (prompt-permitted side effects) doesn't apply to this task
because hidden tests are behavioral, not snapshot-pinned output.

Operational outcomes (no_patch/apply_failed/build_failed) are handled in
test.sh before invoking this script; we only see capability pass/fail here.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import json

junit_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/junit.xml")
exit_code = int(sys.argv[2]) if len(sys.argv) > 2 else 0

def tier_for(testcase):
    name = testcase.get("name", "")
    classname = testcase.get("classname", "")
    file_hint = testcase.get("file", "") + " " + classname
    # bun junit includes classname as file path
    if "model-policy" in file_hint or "model-policy" in name:
        return "adversarial"
    if "fixed-defaults" in file_hint or "model-thinking" in file_hint or "readme" in file_hint.lower():
        return "hidden"
    return "regression"

tests = []
total = passed = failed = 0
hidden_total = hidden_passed = 0
adv_total = adv_passed = 0
regression_total = regression_passed = 0

try:
    tree = ET.parse(junit_path)
    root = tree.getroot()
    for suite in root.iter("testsuite"):
        for case in suite.findall("testcase"):
            total += 1
            name = case.get("name", "unknown")
            classname = case.get("classname", "")
            tid = f"{classname}::{name}" if classname else name
            tier = tier_for(case)
            # failure, error, or skipped?
            has_failure = case.find("failure") is not None or case.find("error") is not None
            status = "failed" if has_failure else "passed"
            tests.append({"id": tid, "tier": tier, "status": status})
            if status == "passed":
                passed += 1
            else:
                failed += 1
            if tier == "hidden":
                hidden_total += 1
                if status == "passed":
                    hidden_passed += 1
            elif tier == "adversarial":
                adv_total += 1
                if status == "passed":
                    adv_passed += 1
            else:
                regression_total += 1
                if status == "passed":
                    regression_passed += 1
except Exception as e:
    print(f"[parse_junit] failed to parse {junit_path}: {e}", file=sys.stderr)
    # Write a fail reward so the verifier doesn't look like success
    reward = {"reward": 0, "outcome": "verifier_error", "reason": f"junit parse failed: {e}", "exit_code": exit_code}
    out_dir = Path("/logs/verifier")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        out_dir = Path("/tmp/verifier")
        out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reward.json").write_text(json.dumps(reward))
    (out_dir / "reward.txt").write_text("0")
    ctrf = {"results": {"summary": {"total": total, "passed": passed, "failed": failed}, "tests": tests}}
    (out_dir / "ctrf.json").write_text(json.dumps(ctrf, indent=2))
    sys.exit(0)

# Reward: all hidden+adversarial must pass AND regression must pass
# (regression is a blocker per TASK-DESIGN §5)
all_hidden_pass = hidden_total > 0 and hidden_passed == hidden_total
all_adv_pass = adv_total > 0 and adv_passed == adv_total
all_reg_pass = regression_passed == regression_total
reward_val = 1 if (all_hidden_pass and all_adv_pass and all_reg_pass) else 0
outcome = "pass" if reward_val == 1 else "fail"

reward = {
    "reward": reward_val,
    "outcome": outcome,
    "tiers": {
        "hidden": {"passed": hidden_passed, "total": hidden_total},
        "adversarial": {"passed": adv_passed, "total": adv_total},
        "regression": {"passed": regression_passed, "total": regression_total},
    },
    "summary": {"total": total, "passed": passed, "failed": failed},
}

# CTRF-ish report
ctrf = {
    "results": {
        "summary": {"total": total, "passed": passed, "failed": failed},
        "tests": tests,
    }
}

out_dir = Path("/logs/verifier")
try:
    out_dir.mkdir(parents=True, exist_ok=True)
except PermissionError:
    out_dir = Path("/tmp/verifier")
    out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "reward.json").write_text(json.dumps(reward, indent=2))
(out_dir / "reward.txt").write_text(str(reward_val))
(out_dir / "ctrf.json").write_text(json.dumps(ctrf, indent=2))
print(f"[parse_junit] {passed}/{total} passed (hidden {hidden_passed}/{hidden_total}, adv {adv_passed}/{adv_total}, reg {regression_passed}/{regression_total}) -> reward {reward_val}")
