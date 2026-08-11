#!/usr/bin/env python3
"""Calibration harness for Task 01: score deliberate partial solutions.

Every entry is a named behavioral scenario; the expected outcome is the
design contract. If any scenario deviates, the harness exits 1 — the bands
are part of the frozen rubric, not decoration.

Scenarios (expected):
  base              0/100   no-op patch earns nothing
  listener-only     5/100   removing just the thinking_level_select listener
  minimal-split    47/100   ownership removed; no warnings/reset/docs
  no-reset-persist 87/100   gold minus persist-active-model-before-delete
  no-legacy-warning 94/100  gold minus the one-time legacy warning
  no-docs           92/100  gold with the base README
  disable           invalid no-op fixed-defaults module (preservation gate)
  alt-structure    100/100  correct behavior, different file organization
  gold             100/100  the reference solution

Usage:
    uv run python calibrate.py \
        [--work /tmp/task01-calibrate] \
        [--node-modules /path/to/node_modules] \
        [--keep]

The harness builds base and gold trees from the task directory itself
(environment/, solution/reference/, tests/hidden/) and runs the same bun
junit + score.py pipeline the verifier uses. It needs bun on PATH and a
node_modules for the bundle (default: the agent-extensions checkout).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
ENV_DIR = TASK_DIR / "environment" / "pi-packages" / "bermudis-pi-goodies"
REFERENCE_DIR = TASK_DIR / "solution" / "reference"
HIDDEN_DIR = TASK_DIR / "tests" / "hidden"
SCORE_PY = Path(__file__).parent / "score.py"

FILES = [
    "fixed-defaults.test.ts", "model-thinking.test.ts", "model-policy.test.ts",
    "bundle-registration.test.ts", "readme-check.test.ts",
    "kilo.test.ts", "prefer-tools.test.ts", "tps.test.ts", "provider-balance.test.ts",
]
HIDDEN_FILES = [
    "fixed-defaults.test.ts", "model-thinking.test.ts", "model-policy.test.ts",
    "bundle-registration.test.ts", "readme-check.test.ts",
]
REFERENCE_FILES = [
    "README.md", "fixed-defaults.ts", "fixed-defaults.test.ts", "index.ts",
    "json-file.ts", "model-policy.test.ts", "model-thinking.test.ts",
    "model-thinking.ts", "bundle-registration.test.ts",
]

EXPECTED = {
    "base": ("scored", 0),
    "listener-only": ("scored", 5),
    "minimal-split": ("scored", 47),
    "no-reset-persist": ("scored", 87),
    "no-legacy-warning": ("scored", 94),
    "no-docs": ("scored", 92),
    "disable": ("invalid", None),
    "alt-structure": ("scored", 100),
    "gold": ("scored", 100),
}


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300, **kw)


def make_tree(work: Path, name: str, src_app: Path | None, node_modules: Path) -> Path:
    d = work / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if src_app is not None:
        shutil.copytree(src_app, d, dirs_exist_ok=True, symlinks=True)
    (d / "node_modules").symlink_to(node_modules, target_is_directory=True)
    return d


def inject_hidden(d: Path):
    for f in HIDDEN_FILES:
        shutil.copy(HIDDEN_DIR / f, d / f)


def score(work: Path, name: str, d: Path) -> tuple[str, int | None]:
    junit = work / f"{name}.junit.xml"
    out_dir = work / "out" / name
    r = run(["bun", "test", "--reporter=junit", f"--reporter-outfile={junit}", *FILES], cwd=d)
    env = dict(__import__("os").environ, SCORE_OUT_DIR=str(out_dir))
    s = run(["uv", "run", "python", str(SCORE_PY), str(junit)], cwd=SCORE_PY.parent, env=env)
    reward = json.loads((out_dir / "reward.json").read_text())
    print(f"  {name}: bun_exit={r.returncode} -> {reward['outcome']} score={reward.get('score')}")
    return reward["outcome"], reward.get("score")


def build_scenarios(work: Path, node_modules: Path) -> dict[str, Path]:
    # curated base app
    base_app = work / "base-app"
    if base_app.exists():
        shutil.rmtree(base_app)
    base_app.mkdir(parents=True)
    shutil.copytree(ENV_DIR, base_app, dirs_exist_ok=True)
    inject_hidden(base_app)

    # gold app = base + reference
    gold_app = work / "gold-app"
    if gold_app.exists():
        shutil.rmtree(gold_app)
    shutil.copytree(base_app, gold_app, symlinks=True)
    for f in REFERENCE_FILES:
        shutil.copy(REFERENCE_DIR / f, gold_app / f)

    trees = {}
    trees["base"] = make_tree(work, "base", base_app, node_modules)
    trees["gold"] = make_tree(work, "gold", gold_app, node_modules)

    # listener-only: drop the thinking_level_select subscription
    d = make_tree(work, "listener-only", base_app, node_modules)
    p = d / "fixed-defaults.ts"
    t = p.read_text()
    assert 'pi.on("thinking_level_select"' in t
    p.write_text("\n".join(l for l in t.splitlines() if 'pi.on("thinking_level_select"' not in l))
    trees["listener-only"] = d

    # minimal split: ownership out of config/restore/set/events; status/warn/reset/docs untouched
    d = make_tree(work, "minimal-split", base_app, node_modules)
    p = d / "fixed-defaults.ts"
    t = p.read_text()
    t = t.replace("""  if (input.thinkingLevel !== undefined) {
    if (!isThinkingLevel(input.thinkingLevel)) {
      throw new Error(
        `\\`thinkingLevel\\` must be one of: ${ALL_LEVELS.join(", ")}`,
      );
    }
    override.thinkingLevel = input.thinkingLevel;
  }
""", "")
    t = t.replace("""    const hasThinkingPin = override.thinkingLevel !== undefined;
    if (!hasModelPin && !hasThinkingPin) return;
""", "    if (!hasModelPin) return;\n")
    t = t.replace("""    if (hasThinkingPin) {
      settings.setDefaultThinkingLevel(override.thinkingLevel!);
    }
""", "")
    t = t.replace("""        const level = pi.getThinkingLevel();
        const override: FixedDefaultsOverride = {
          provider: model.provider,
          model: model.id,
          thinkingLevel: level,
        };
""", """        const override: FixedDefaultsOverride = {
          provider: model.provider,
          model: model.id,
        };
""")
    t = t.replace("""          `Pinned ${model.provider}/${model.id} · thinking ${level} as startup defaults`,
""", """          `Pinned ${model.provider}/${model.id} as the startup model`,
""")
    t = t.replace('  pi.on("thinking_level_select", (_event, ctx) => schedule(ctx));\n', "")
    p.write_text(t)
    trees["minimal-split"] = d

    # gold minus reset persist
    d = make_tree(work, "no-reset-persist", gold_app, node_modules)
    p = d / "fixed-defaults.ts"
    t = p.read_text()
    t = t.replace("""            // Save the active model before removing the pin. Otherwise the
            // old pinned model remains in settings.json and wins at the next
            // fresh start.
            await persistModel(ctx, model.provider, model.id);
""", "")
    p.write_text(t)
    trees["no-reset-persist"] = d

    # gold minus legacy warning
    d = make_tree(work, "no-legacy-warning", gold_app, node_modules)
    p = d / "fixed-defaults.ts"
    t = p.read_text()
    t = t.replace("""      if (legacyThinkingLevel && !this.warnedLegacyThinkingLevel) {
        console.warn(
          `[fixed-defaults] legacy thinkingLevel found in ${this.path}; it is ignored. Add the policy to model-thinking.json instead.`,
        );
        this.warnedLegacyThinkingLevel = true;
      }
""", "")
    p.write_text(t)
    trees["no-legacy-warning"] = d

    # gold minus docs
    d = make_tree(work, "no-docs", gold_app, node_modules)
    shutil.copy(base_app / "README.md", d / "README.md")
    trees["no-docs"] = d

    # disabled fixed-defaults
    d = make_tree(work, "disable", gold_app, node_modules)
    (d / "fixed-defaults.ts").write_text(
        "/** Disabled. */\n"
        "export default function fixedDefaults(): void {}\n"
    )
    trees["disable"] = d

    # alternative structure: no shared json-file.ts, helpers duplicated inline
    d = make_tree(work, "alt-structure", gold_app, node_modules)
    (d / "json-file.ts").unlink()
    helpers = """
function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function writeJsonAtomic(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.${Date.now()}.tmp`;
  try {
    writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\\n`, { encoding: "utf8", mode: 0o600 });
    renameSync(temporaryPath, path);
  } catch (error) {
    try { unlinkSync(temporaryPath); } catch { /* absent */ }
    throw error;
  }
}

function unlinkIfPresent(path: string): boolean {
  try { unlinkSync(path); return true; }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return false; throw error; }
}
"""
    for mod in ["fixed-defaults.ts", "model-thinking.ts"]:
        p = d / mod
        t = p.read_text()
        t = t.replace('import {\n  describeError,\n  unlinkIfPresent,\n  writeJsonFileAtomic,\n} from "./json-file.ts";\n', "")
        t = t.replace("writeJsonFileAtomic(this.path", "writeJsonAtomic(this.path")
        t = t.replace("writeJsonFileAtomic(", "writeJsonAtomic(")
        t = t.replace(
            'import { readFileSync, statSync } from "node:fs";',
            'import { mkdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from "node:fs";\nimport { dirname, join } from "node:path";\n' + helpers,
        )
        p.write_text(t)
    trees["alt-structure"] = d
    return trees


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/tmp/task01-calibrate"))
    ap.add_argument("--node-modules", type=Path,
                    default=Path.home() / "build" / "agent-extensions" / "pi-packages" / "bermudis-pi-goodies" / "node_modules")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if not args.node_modules.exists():
        print(f"node_modules not found at {args.node_modules} — pass --node-modules", file=sys.stderr)
        return 1

    if args.work.exists() and not args.keep:
        shutil.rmtree(args.work)
    args.work.mkdir(parents=True, exist_ok=True)

    trees = build_scenarios(args.work, args.node_modules)
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
