# AGENTS.md

## Project

A benchmark for frontier LLM agents on **dense systems-programming tasks** —
implementing real standards (DNS, DEFLATE, WASM, Raft) clean-room in
library-poor languages, graded by deterministic tests. The question this
benchmark answers is not "can the model write 5,000 LOC?" but "can it maintain
correctness across a compact but unforgiving system where every wrong
assumption is punished by deterministic tests?"

Current state: design doc only (`Clean Room TCP Benchmark - Poe - poe.com.md`).
No harness, no tasks implemented yet.

## Design Principles

These are **red lines**. Any task or harness change that violates them is wrong
by definition.

- **Determinism over realism.** No live network, no wall-clock dependencies,
  no platform-specific behavior. Tasks that would require these (live DNS,
  JIT executable memory) are replaced with offline simulations or subset
  interpreters.
- **Isolation between tasks.** Each task tests one capability. Do not chain
  dependencies (e.g. Git packfile after DEFLATE, PNG after DEFLATE) — failure
  must not compound across tasks. If a task needs a primitive another task
  covers, the harness provides a trusted version.
- **Anti-contamination via hidden adversarial tests, not language scarcity.**
  Using Zig/Nim/V reduces `pip install solved_problem` but does not prevent
  translation from C/Rust/Go. The real defense is: you can copy the happy path,
  but hidden edge cases expose you.
- **Sandbox enforcement.** Each task runs in a Docker sandbox with no network,
  no third-party packages, no subprocess escape hatches (`tar`, `gzip`, `git`,
  `sqlite3`, ...). Suspicious subprocess calls must fail.
- **Single-binary CLI contract.** Every task is invoked as
  `./solution <subcommand> <input> [output]`. Deterministic output format.
  No long-running servers, no GUIs.

## The 10 Tasks

This is the contract. Names and order are stable; scope details live in the
design doc and per-task specs.

| # | Task | Capability |
|---|------|-----------|
| 1 | DNS Packet Codec | Binary serialization, name compression, malformed-packet defense |
| 2 | POSIX ustar Reader/Writer | File format, octal fields, checksums, block alignment |
| 3 | RV32I Emulator | Bit decoding, CPU state, sign extension, branches |
| 4 | Thompson Regex Engine | Automata, parser + graph execution, no catastrophic backtracking |
| 5 | DEFLATE Decompressor | Bitstream parsing, canonical Huffman, LZ77 |
| 6 | SQL-on-CSV Executor | Parser, planner logic, type handling, relational semantics |
| 7 | LSM-Tree KV Store | WAL, memtable, SSTables, tombstones, compaction, restart recovery |
| 8 | MiniCommonMark Parser | Text grammar, indentation, recursive structures, ambiguity |
| 9 | WebAssembly Subset Interpreter | Binary VM, stack machine, integer ops, calls, branches, memory |
| 10 | Deterministic Raft State Machine | Distributed state-machine reasoning — the "boss fight" |

Task 10 may be deferred from v1; the rest are v1.

### Task-specific scope notes (stable)

- **DNS (1):** Offline resolver simulation over a harness-provided "DNS
  universe." Never hit real resolvers. Record types: A, AAAA, CNAME, MX, TXT,
  NS.
- **Regex (4):** Literals, groups, alternation, quantifiers, char classes.
  Thompson/NFA construction — backtracking engines that hang on adversarial
  input fail by design.
- **DEFLATE (5):** Raw DEFLATE; zlib/gzip wrapper is bonus only.
- **SQL (6):** `SELECT`, `WHERE`, `JOIN`, `GROUP BY`, aggregates, `ORDER BY`,
  `LIMIT`.
- **LSM (7):** Adversarial workload traces (mass delete → compaction → crash
  → restart → read) are in scope. WAL recovery is a required capability.
- **MiniCommonMark (8):** Defined subset — see design doc §4. Grade by
  normalized AST or normalized HTML, **not** raw string diff. Exclude raw HTML
  passthrough, obscure link-reference edge cases, Unicode normalization.
- **WASM (9):** MVP subset. Integer ops, locals, (globals maybe), function
  calls, branches, memory load/store. Replaces the original JIT Brainfuck
  proposal — do not reintroduce JIT tasks.
- **Raft (10):** Pure simulated messages and ticks. Harness owns fake time,
  message delivery, partitions, drops, restarts, persistence fault injection.
  The model implements only the state machine:
  `new_node` / `tick` / `receive` / `client_append` / `inspect`.

## Test Data Strategy

Three tiers per task. Sourcing details in design doc §"Where to get data."

| Tier | Weight | Source |
|------|--------|--------|
| Public smoke tests | ~10% | 5–10 happy-path examples in the prompt — define the I/O format |
| Hidden standard tests | ~40% | Official spec suites (CommonMark spec.txt, WASM `test/core`, `riscv-tests`, RE2/Glushkov, SQLite `sqllogictest`) |
| Adversarial / malformed | ~50% | OSS-Fuzz corpora, `radamsa`-mutated binaries, path-traversal tarballs, Raft event traces from Ongaro's dissertation figures |

A model that memorized a reference implementation should pass tiers 1–2 and
**fail violently** on tier 3 (segfault, infinite loop, or wrong output).

## Scoring

Beyond pass/fail. Suggested weights: 40% normal fixtures, 40% hidden edge
cases, 10% malformed-input handling, 5% performance threshold, 5% sandbox
compliance. Also track wall-clock time, tokens, tool calls, compile attempts,
test attempts, final LOC, file count.

### Efficiency-frontier reporting

`harness/report.py` aggregates `bench-*.json` runs into efficiency-frontier
charts (score vs cost / tokens / wall-clock, one point per
model+lang+thinking config, median over trials) rather than reporting raw
medians — the point is to surface that efficiency varies by orders of
magnitude with no strong correlation to score. This is host-side reporting
only; it never touches the sandbox or grading. Output goes to a fresh
`mktemp` dir by default (path printed to stdout) to keep task dirs clean.

**OPEN — how to treat 0.0-score trials in aggregation.** A 0.0 is recorded for
two causes the benchmark does not yet distinguish: capability failure (wrote a
solution, scored 0) and operational failure (no solution produced: cost cap,
crash, never committed a build file). Both fold into the median today. Counting
them is the conservative default — dropping operational failures would flatter
unreliable configs. Decision deferred until a trajectory failure taxonomy tags
each 0.0 with a category, at which point a per-cause policy becomes data-driven.
Mirrored as a comment at `harness/report.py:aggregate()`.

### Isolated verification

Grading is isolated from the agent's runtime state (DeepSWE-style): each test
case runs in a fresh hardened `docker run --rm` container against a corpus the
agent never sees. When `run.py --solution <dir>` is given, only source is
staged into `tasks/<task>/solution/candidate/` — reset each run — and the
Dockerfile COPYs that. The filter keeps source dirs (`src/`, `lib/`) and
source/build files by extension (`.c .h .zig .nim .v .zon .rs .go` +
`Makefile`/`build.zig`); the agent's scratch — compiled binaries (incl. the
bare `solution` binary), `sessions/`, `trajectory.jsonl`, `*.bin`/`*.json`
fixtures, `broken/`, `reference/`, caches — never reaches the grading build.
The reference/ oracle used by `gen_tests.py` stays out of the build entirely.
The 5% sandbox score is attested from the actual `docker run` hardening flags
emitted, not asserted.

## Workflow

Task 01 (DNS Packet Codec) is implemented end-to-end as the vertical slice.
The harness, scorer, Docker sandbox, and three-tier test pipeline are all
working. See `TEMPLATE.md` for how to add tasks 2–10.

### Build & Test Commands

```bash
# Build the reference solution (Zig 0.16)
cd tasks/01-dns/solution/reference && zig build -Doptimize=ReleaseFast

# Generate test fixtures + manifests (uses reference as oracle)
python3 tasks/01-dns/harness/gen_tests.py tasks/01-dns \
    tasks/01-dns/solution/reference/zig-out/bin/solution

# Run the full harness (builds Docker image + runs all tiers + scores)
python3 harness/run.py tasks/01-dns --solution tasks/01-dns/solution/reference

# Run without rebuilding the Docker image
python3 harness/run.py tasks/01-dns --solution tasks/01-dns/solution/reference --no-build

# Run a single tier
python3 harness/run.py tasks/01-dns --tier adversarial --no-build
```

### Current State (Task 01)

- Language: **Agent's choice — C (gcc + make) or Zig 0.16.** Both toolchains
  are installed in the sandbox and grading images. The grading Dockerfile
  auto-detects the build system (Makefile → make, build.zig → zig build).
  This lets us compare the same model's C vs Zig solutions side-by-side:
  Zig 0.16 is unfamiliar to all current models (released after training
  cutoffs), so it tests reasoning from first principles vs. recall.
- Reference solution (Zig): 40/40 tests pass, SCORE: 100.0%
- Test fixtures are language-agnostic (`.bin` packets, `.expected.json`).
- Docker sandbox: `--network none --read-only --memory 256m --cpus 1
  --cap-drop ALL --security-opt no-new-privileges`
- Budget control: `--max-cost` (default $1.00) aborts the agent when spend
  exceeds the threshold. `--max-time` defaults to 0 (no time cap) — use
  cost as the primary budget constraint.
- Agent runs (DeepSeek v4-pro via OpenRouter, DeepSeek lab provider):
  - Zig, `high` thinking, 30min cap: 37/40, SCORE: 88.0% — passes all public
    + adversarial, fails 3 hidden (AAAA formatting, 2 roundtrip cases).
    ~1400 LOC, 30 min (hit time cap).
  - Zig, `xhigh` thinking, 30min cap: 37/40, SCORE: 88.7% — passes 9/10
    hidden but only 6/22 adversarial (exit code 1 instead of 2 on malformed).
    Spent 25/30 min on Zig 0.16 compile errors, never tested adversarial.
  - C, `high` thinking, 30min cap: 30/40, SCORE: 82.2% — passes all public,
    6/10 hidden, 18/22 adversarial. Failed rdata length validation (a13-a16).
    128 tool calls, 57 test runs, $0.16, 23 min (finished before cap).

### Agent Harness (bench.py)

The agent harness runs an LLM agent against a task in a Docker sandbox,
then grades the result with run.py. Architecture:

- **Pi** (the coding agent) runs on the host in RPC mode (`--mode rpc`)
- **Sandbox container** has the compiler + spec + public tests, no network
- Pi's `write`/`edit` tools create files in a host dir bind-mounted at
  `/workspace` in the container
- Pi's `bash` tool runs `docker exec <container> sh -c '...'` to compile/test
- After the agent finishes, `run.py --solution <work_dir>` grades the result
- OpenRouter provider routing is pinned via Pi's `models.json`
  (`compat.openRouterRouting` → OpenRouter's `provider` field)

```bash
# Run an agent against Task 01 (builds sandbox image, runs agent, grades)
# --lang forces C or Zig. No time cap by default; cost cap at $1.00.
python3 harness/bench.py tasks/01-dns \
    --model openrouter/deepseek/deepseek-v4-pro \
    --provider-order deepseek --no-fallbacks \
    --thinking high --lang c --max-turns 100 --max-cost 1.00

# Same task, forcing Zig 0.16
python3 harness/bench.py tasks/01-dns \
    --model openrouter/deepseek/deepseek-v4-pro \
    --provider-order deepseek --no-fallbacks \
    --thinking high --lang zig --max-turns 100 --max-cost 1.00

# Skip sandbox image rebuild (use existing image)
python3 harness/bench.py tasks/01-dns --no-build \
    --model openrouter/deepseek/deepseek-v4-pro ...

# Keep sandbox container for debugging after the run
python3 harness/bench.py tasks/01-dns --keep-sandbox \
    --model openrouter/deepseek/deepseek-v4-pro ...

# Verbose mode (print all Pi events)
python3 harness/bench.py tasks/01-dns --verbose \
    --model openrouter/deepseek/deepseek-v4-pro ...
```

Key files:
- `harness/bench.py` — benchmark runner (orchestrates agent + sandbox + grading)
- `harness/lib/pi_client.py` — Pi RPC client (manages subprocess, collects metrics)
- `harness/lib/sandbox.py` — Docker sandbox manager (creates/stops containers)
- `tasks/01-dns/harness/Dockerfile.sandbox` — sandbox image (compiler, no solution)
- `tasks/01-dns/harness/Dockerfile` — grading image (bakes solution in at build time)

## Constraints & Red Lines

- **No live networking in any task.** DNS, NTP, HTTP fetch, etc. must be
  simulated by the harness.
- **No platform-specific JIT.** No `mmap` with executable permissions, no
  machine-code emission. Use bytecode VMs / interpreters instead.
- **No task-to-task dependency chains.** Each task is graded independently.
- **No third-party packages, no subprocess shells** in the sandbox.
- **Grade MiniCommonMark on normalized output**, never raw string diff.
