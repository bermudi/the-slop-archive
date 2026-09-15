#!/usr/bin/env python3
"""score.py — Track B reward computation (v3).

Input: JSON file on argv[1] (see selftest_gate.sh for the schema), with the
parsed baseline_manifest.json embedded under "manifest". Prints reward.json
to stdout. Keeping the arithmetic here (not in a shell heredoc) is what makes
the gate adversarially testable without a device.

Gate semantics — the hard line (identity preservation):
  preserve    = every ROM in manifest.baseline_passes still passes, BY NAME.
  regressions = baseline_passes that now fail  -> any one zeroes ALL speed
                credit. Trading a fix for a break is visible and fatal;
                doing nothing and breaking something score the same speed
                (zero) — conservative non-work is never rewarded ABOVE work.
  new_fixes   = scored ROMs the baseline failed that now pass -> counted in
                the correctness term, reported separately.
  correct     = preserve AND still_renders AND challenge signature.
  flaky       = manifest ROMs that were <100% stable in the campaign ->
                excluded from gate and denominator, reported.
Overspeed (hard line): app_fps > 59.7275*1.02 -> app credit zero. An app
presenting faster than realtime is a broken product (pacing), not a fast
one. Headless overspeed remains legitimate — that is capacity, not pacing.
"""
import json
import sys

GBFPS = 59.7275
APP_MAX = GBFPS * 1.02  # ~60.92: pacing ceiling; above it app credit is zero


def main():
    inp = json.load(open(sys.argv[1]))
    man = inp["manifest"]
    flaky = man.get("flaky", [])
    suite = [r for r in man["suite"] if r not in flaky]
    res = inp.get("rom_results", {})
    passes = [r for r in suite if res.get(r) == 1]
    regressions = [r for r in man["baseline_passes"] if res.get(r) != 1]
    new_fixes = [r for r in suite if r not in man["baseline_passes"] and res.get(r) == 1]
    preserve = int(not regressions)

    roms = len(passes) / len(suite) if suite else 0.0
    vroms = roms if inp["challenge"] == 1 else 0.0
    correct = int(preserve == 1 and inp["renders"] == 1 and inp["challenge"] == 1)

    def clamp(x):
        return max(0.0, min(1.0, x))

    emu_fps, app_fps = inp["emu_fps"], inp["app_fps"]
    overspeed = int(app_fps > APP_MAX)
    app_imp = 0.0 if overspeed else clamp((app_fps - inp["base_app"]) / (GBFPS - inp["base_app"]))
    emu_imp = clamp((emu_fps - inp["base_emu"]) / (GBFPS - inp["base_emu"]))
    speed = 0.50 * app_imp + 0.20 * emu_imp

    m = {
        "artifact_present": inp["artifact"],
        "lint_clean": inp["lint"],
        "stream_verified": 1,
        "bench_variants": 2,
        "challenge_sig": inp["challenge"],
        "emu_fps": round(emu_fps, 1),
        "emu_speedup": round(emu_fps / GBFPS, 3),
        "app_fps": round(app_fps, 1),
        "app_cpu_pct": inp["cpu"],
        "still_renders": inp["renders"],
        "test_roms": round(roms, 3),
        "verified_roms": round(vroms, 3),
        # v3 gate: identity preservation, reported in full
        "preserve": preserve,
        "regressions": regressions,
        "new_fixes": new_fixes,
        "flaky_diagnostic": flaky,
        "rom_results": {k: res.get(k, 0) for k in man["suite"]},
        "trap_diagnostic": inp.get("trap_diagnostic"),
        "overspeed": overspeed,
        "realtime": int(55 <= app_fps <= APP_MAX),
        "app_improvement": round(app_imp, 3),
        "emu_improvement": round(emu_imp, 3),
        "anchor": inp["anchor"],
        "anchor_base_emu": round(inp["base_emu"], 1),
        "anchor_base_app": round(inp["base_app"], 1),
        "manifest_runs": man.get("runs", 0),
    }
    m["score"] = round(0.30 * vroms + (speed if correct else 0.0), 3)
    print(json.dumps(m))


if __name__ == "__main__":
    main()
