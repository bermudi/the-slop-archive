# Task Design Guide

How to design tasks for this benchmark — and what to avoid. This document
distills the practices from three sources, adapted to our Harbor + pi stack.

This is a **personal benchmark** — no paper, no public leaderboard. Where
the sources prescribe heavyweight process for credibility (human review
boards, multi-layer QC), this guide keeps the *mechanism* and drops the
*ceremony*: §10 marks what to relax and what must survive. The short
version: relax anything whose cost scales with the number of tasks and
exists to convince strangers; keep anything that makes a single score true.

- **DeepSWE v1** (datacurve.ai) — contamination-free long-horizon tasks,
  behavioral verification, judge-audited grading quality
- **DeepSWE v1.1** — isolated patch grading, structured per-test reports,
  natural git environments
- **FrontierCode** (cognition.com) — mergeability rubrics, adversarial
  self-audits ("hack reports"), rubric calibration

Plus hard-won lessons from this repo's own legacy runs (on the `legacy`
branch) and from building Task 01.

---

## 1. What a task is

Every task is a Harbor recipe — five artifacts, exactly one of which the
agent sees fully:

```
tasks/<NN>-<slug>/
├── task.toml          # Metadata: timeouts, resources, network policy
├── instruction.md     # The prompt. The ONLY prose the agent reads.
├── environment/
│   └── Dockerfile     # The agent's sandbox: codebase at base state,
│                      # toolchain, public fixtures. No network.
├── tests/             # The verifier. HELD OUT — never in the sandbox.
│   ├── test.sh        #   entry point → writes reward
│   └── ...            #   held-out cases, fixtures, graders
└── solution/          # Reference implementation. HELD OUT — used for
                       # calibration and review, NEVER at grading time.
```

Two sandbox rules that are non-negotiable here:

- `network_mode = "no-network"` in `[environment]` — no live network, ever.
  If a task seems to need one (DNS, HTTP), simulate it offline.
- `verifier.environment_mode = "separate"` — the agent's work is extracted
  as a patch/diff and graded in a pristine container. The verifier never
  shares a filesystem with the agent's runtime state.

---

## 2. The contract (red lines)

These override everything else in this document. A task that violates one
is wrong by definition.

1. **Determinism over realism.** No wall-clock dependencies, no live
   network, no platform-specific behavior. If a test can pass or fail
   depending on *when* it runs or *what state the host is in*, it is not a
   test — it is a coin flip. (We have a live example of this sin in our own
   codebase: a cache-TTL test that reads the developer's real
   `~/.pi/agent/cache/provider-balance.json` and passes or fails depending
   on whether pi refreshed the cache in the last 30 minutes. It flipped
   while we were watching. Never do this.)
2. **One capability per task.** Failure must not compound across tasks. If
   a task needs a primitive another task covers (compression, parsing), the
   environment provides a trusted version.
3. **Grade observable behavior, never implementation.** The verifier
   accepts any solution whose externally visible behavior is correct —
   different module boundaries, helper names, control flow, all fine.
4. **The agent cannot reach the answer.** No reference solution in the
   sandbox. No gold patch in git history. No held-out test files.
5. **Novel, not recalled.** Tasks are written from scratch or derived from
   private context (like our pi session transcripts) that no model has
   trained on. Never adapt an existing public PR/commit — the solution is
   already online.

---

## 3. Designing the task

### Pick real work, not puzzle problems

The best task sources, in order:

1. **Real engineering sessions** — work someone (or an agent) actually did:
   a refactor to eliminate dual ownership, a migration, a bug with a subtle
   root cause. Our Task 01 comes from a pi session where a real diagnosis
   ("two modules both own thinking level") led to a real fix.
2. **Unresolved issues in active repos** — motivated by a real GitHub issue,
   but the fix is written fresh (DeepSWE's model).
3. **Last resort: synthetic** — only if it exercises the same decisions as
   real work. Codec-from-spec tasks are the exception: a standard like
   DEFLATE *is* the specification, and the task is implementing it.

### Size it right

- Target **20–60 minutes** for a strong agent. FrontierCode's data point:
  difficulty comes from *quality standards*, not patch size. A 50-line
   diff with a subtle behavioral requirement beats a 500-line diff of
  mechanical work.
- The task must force **discovery**: finding where the change belongs,
  weighing design tradeoffs, understanding existing conventions. If the
  prompt tells the agent exactly which file and function to edit, you've
  tested code generation, not engineering.
- Include **multi-part requirements** ("support both sync and async",
  "line comments *and* block comments"). DeepSWE's failure analysis shows
  these separate models reliably — forgetful agents ship one branch and
  miss its mirror. Two-thirds of Claude's missed-requirement failures fit
  this "one branch shipped" pattern. Design for it deliberately: it's a
  feature, not a trap, as long as the requirement is *stated*.

### Novelty check

Before accepting a task, ask: could a model pass this by recall? If the
task is "implement DEFLATE," the answer is *partially* — happy paths are
memorized. That's what held-out adversarial tests are for (§5). But if the
*entire* task is a well-known implementation with a public test suite, it
measures memory, not problem-solving.

---

## 4. Designing the prompt (`instruction.md`)

### Rules

- **Short and natural.** Write it the way a developer would message an
  agent: behavior-focused, no interface-definition blocks, no numbered todo
  lists. DeepSWE prompts are half the length of SWE-bench Pro's with tasks
  that require 5.5× more code. FrontierCode's are a third.
- **Describe symptoms and requirements, not the solution.** "Sessions start
  on the wrong model" + constraints. Not "remove `thinkingLevel` from
  `FixedDefaultsOverride`." The discovery *is* the task.
- **Two parts.** (1) The task description. (2) The codebase conventions —
  how to build, test, lint, what style to follow — exactly as an AGENTS.md
  would give them. A new contributor gets both; the agent should too.
- **State every graded requirement.** If the verifier tests it, the prompt
  must ask for it. An unstated requirement is a false-negative machine
  (§8).

### Never

- **Never mention the verifier, held-out tests, or grading.** One
  catastrophic line from SWE-bench Pro: "do not modify the testing logic or
  any of the tests." Agents took it as license to never write tests at all
  — test-writing collapsed from 80%+ of runs to 3–28%. DeepSWE's prompts
  say nothing about tests, and self-verification behavior came back.
  The prompt shapes the agent's process; silence about grading is the
  correct shape.
- **Never name internal symbols** the verifier will check — the verifier
  doesn't check symbols at all (§5), and naming them in the prompt both
  over-specifies the solution and leaks the reference implementation's
  structure.
- **Never include reproduction code that does the agent's work** — a
  repro *script* is fine (it's how developers work), but if the prompt's
  example is 90% of the patch, the task is dead.

---

## 5. Designing the verifier (`tests/`)

The verifier is the benchmark. DeepSWE's audit found SWE-bench Pro's
verifier disagrees with careful human judgment on **32% of trials** (8%
false positives, 24% false negatives); a hand-built behavioral verifier
disagrees on 1.4%. Everything below exists to close that gap.

### The core rule: behavior through public interfaces

Tests assert what the system *does* — CLI output, API responses, file
contents, exit codes, state transitions — never *how*: no imports of
private helpers, no internal state inspection, no exact symbol names.

**Why this matters concretely** (real SWE-bench Pro failure): the gold PR
factored out a private helper `parseRpmQfLine`; the test imported it. An
agent that solved the task by inlining the same logic failed to *compile*
— false negative. A behavioral test ("parse this rpm output, produce this
structure") accepts both.

### Prompt-verifier bijection

The verifier tests **exactly** what the prompt asks: no more (false
negatives — agent solved the stated task but failed an unstated one), no
less (false positives — partial solutions scored as complete). Write the
prompt and the verifier against each other, in the same sitting.

### Acceptance breadth

For every task, the author must write **at least one alternative solution**
that differs structurally from the reference (different module split,
inlined logic, different helper names). If the verifier rejects it, the
verifier is too rigid. This is FrontierCode's "hack report" in the
false-negative direction, and it's the single highest-value QC step.

### Regression safety

Every verifier run includes the repo's **existing test suite** (the subset
that's deterministic) plus any regression tests the author adds. A patch
that implements the feature but breaks unrelated behavior fails. Real
contributions don't get to break the build.

### Determinism requirements (hard)

- Run the verifier **three times** during authoring. Any variance → the
  verifier is flaky → returned for revision. Verifier noise shows up as
  model variance in scores; it's the worst kind of bug because it looks
  like signal.
- No wall-clock assertions, no TTLs against real time, no reading of
  host state (`~/`, env-dependent paths), no network. Freeze time if the
  domain needs it (inject a clock; assert against injected values).
- Hermetic: the verifier container builds from the task directory alone.
  Dependency versions pinned. If `bun install` or `apt-get` must fetch,
  vendor the artifacts into the image build.

### Structured, per-test reporting

Emit a machine-readable report (CTRF-style: every task-defining test by
name + status). This is how you catch **gaming by omission**: an agent
that deletes tests, monkey-patches the framework, or forces an early exit
shows up as *missing* results, not passes. Aggregate pass/fail alone is
gameable; a per-test ledger is not.

### Tiers

Keep the old benchmark's three-tier instinct, expressed as verifier cases:

| Tier | Visible to agent? | Purpose |
|------|-------------------|---------|
| Public | Yes (in environment) | Define the I/O contract; happy path |
| Held-out | No | Standard conformance; the bulk of the score |
| Adversarial | No | Malformed input, edge cases, the behaviors memorized solutions get wrong |

The adversarial tier is the anti-contamination defense: a model that
memorized a reference implementation passes public + held-out and fails
adversarially — wrong exit codes, no defense against degenerate input,
missing the mirror branch of a dual requirement.

### Blockers vs. quality signals

Borrow FrontierCode's split when a task has quality dimensions beyond
correctness:

- **Blockers** — hard stops: behavioral correctness, regression safety,
  scope discipline (the patch touches only what it needs). Failing any
  blocker → score 0.
- **Non-blockers** — weighted quality signals: test quality, code quality,
  convention adherence. The score aggregates these *only if* all blockers
  pass.

Two FrontierCode mechanisms worth adopting where they fit:

- **Reverse-classical check**: if the agent is expected to write tests,
  run *their* tests against the base (broken) codebase — they must fail.
  A test that passes against the broken code tests nothing.
- **Scope check**: automated diff constraints (files allowed/denied, size
  limits). Restraint is part of the task.

---

## 6. Designing the environment (`environment/Dockerfile`)

- **Reproduce the base state faithfully.** The codebase at its pre-change
  commit, toolchain installed, dependencies vendored, public fixtures in
  place. If deriving from a real repo: shallow clone, `main` at the base
  commit, **all future history deleted** (v1.1's "natural git environment"
  — agents work on main and branch normally, but there is no gold commit
  to find).
- **No gold anywhere.** Not in git history, not in a `reference/` dir in
  the image, not in file comments. SWE-bench Pro's most embarrassing
  failure mode: agents ran `git log --all` / `git show <hash>` and pasted
  the merged fix. 87% of Claude's flagged cheats were exactly this. Our
  defense is structural: there is no gold to find.
- **Pre-install everything.** No network means `bun install` /
  `cargo build` can't fetch — `node_modules`, cargo registries, apt
  packages are baked in at image build time. Test the image with
  `network_mode = "no-network"` *before* shipping the task.
- **Comfortable, not hostile.** Enough RAM/CPU for the toolchain (a bundler
  on 256MB is an environment bug, not a difficulty setting), a writable
  workspace, sane PATH. DeepSWE's cleanliness rule: when an agent fails,
  the failure must come from the task, not the environment.

---

## 7. The reference solution (`solution/`)

- Write it **alongside** the prompt and verifier, from scratch.
- It is **never** used at grading time. It exists so reviewers can
  spot-check that the task is solvable and the verifier accepts a correct
  answer, and so calibration runs have a known-100% artifact.
- Never merged upstream, never published with the task pack. If the task
  derives from a private session (our Task 01), the "reference" is the
  shipped implementation — proven correct by its own test suite, which is
  even better.

---

## 8. What to avoid — the taxonomy

### False positives (wrong solution passes)

| Failure | Mechanism | Defense |
|---------|-----------|---------|
| **Gold leak** | Agent finds the reference in git history or the image | Shallow clone, no future history, solution/ held out, grade only the extracted patch in a separate container |
| **Weak tests** | Tests only exercise the happy path; stubs and no-ops pass | End-to-end behavioral assertions; adversarial tier; hack report (§9) |
| **Monkey-patching the grader** | Agent edits the test framework, forces early exit | Verifier runs in a *separate* container from a *committed patch*; per-test CTRF ledger makes dropped tests visible |
| **Scope violation rewarded** | Patch solves it by rewriting half the repo, breaking conventions | Scope criteria (file/size constraints), regression suite |

### False negatives (correct solution fails)

| Failure | Mechanism | Defense |
|---------|-----------|---------|
| **Private-symbol imports** | Test imports the reference's internal helper; a differently-factored correct solution doesn't compile | Behavioral tests only — public APIs, CLI, files, exit codes |
| **Fixture doesn't ride along** | Verifier restores the test file but not its fixture data | Fixtures live with the verifier, all of it held out, nothing "restored" piecemeal |
| **Unrelated tests in the verifier** | Gold-test set sweeps in tests that don't exercise the asked-for change; a correct fix with any side effect fails | Verifier tests exactly the prompt's requirements (bijection), regression suite is the *repo's own* suite, kept separate from the task-defining tests |
| **Exact-string matching** | Verifier diffs raw stdout including wording the prompt never pinned | Assert structure and semantics (parse the JSON, check the keys), never prose; if exact output is required, the prompt must say so and show it |

### Environment noise

- **Wall-clock anything.** The canonical sin (our TTL test). No `Date.now()`
  in graded paths, no real-time TTLs, no sleeps whose duration affects
  assertions. DeepSWE v1.1 even *stopped reporting wall-clock as a metric*
  because host performance and provider load make it noise. We track it for
  interest but never score it.
- **Dependency drift.** Unpinned `apt`/`npm`/`bun` installs mean the task
  changes over time. Pin versions; vendor artifacts; verify the image
  builds offline.
- **Host-state leakage.** Tests reading `$HOME`, `/tmp` leftovers, or
  developer machine files. The container must be the whole world.

### Prompt pathologies

- **The todo list.** "1. Add field X to struct Y. 2. Update function Z..."
  — you've written the solution and taxed the agent for typing it. State
  the behavior; let the agent engineer.
- **Interface dumps.** Giant blocks of "here are the exact types and
  signatures" — over-specification that kills the discovery signal.
- **"Don't touch the tests."** Suppresses the single most predictive good
  behavior (self-verification). Say nothing about tests.
- **Ambiguity as difficulty.** Terse ≠ good. Behavioral verification needs
  enough specificity to know what surface to test. If two reasonable
  engineers would build different observable behaviors, the prompt is
  under-specified — and the verifier will false-negative one of them.

### Scoring pathologies

- **Binary-only scoring on rich tasks.** If a task has quality dimensions,
  pass/fail alone hides the signal; use blockers + weighted non-blockers.
- **Scoring efficiency metrics with noise.** Cost and tokens are stable
  enough to compare (they vary by an order of magnitude across models with
  no strong correlation to score — that's a finding). Wall-clock is not.
- **Verifying effort instead of outcome.** Line counts, "did they use
  pattern X" — measures matching the author's taste, not solving the task.

---

## 9. Quality control pipeline

A task enters the benchmark only after passing all five gates:

1. **Authoring** — prompt, environment, verifier, and reference solution
   written together, prompt↔verifier bijection checked in the same sitting.
2. **Flakiness check** — verifier runs 3× on the reference solution and 3×
   on the base state (must fail there — the reverse check). Any variance →
   back to the author.
3. **Hack report** — the author (or another agent) attacks the task:
   - *Lazy/adversarial direction*: try to get a passing score with a
     deliberately wrong, stubbed, or partial solution. Any pass = false
     positive = verifier gap.
   - *Valid-alternative direction*: write a correct solution with a
     *different structure* than the reference. Any fail = false negative =
     verifier too rigid.
4. **Calibration** — solutions targeting ~0%, ~33%, ~66%, ~100% scores. If
   the verifier can't resolve the difference, it has no resolution and the
   rubric/tiers need work.
5. **Review** — someone other than the author inspects the prompt,
   verifier, reference, and at least one failing diagnostic rollout.
   Near-correct failing rollouts are the most valuable artifact there is:
   they show exactly how the verifier behaves at the edge.

---

## 10. Relaxation guide (personal benchmark)

Sorted by effort saved. The first group is pure ceremony for credibility —
cut freely. The second group survives not because it's rigorous-looking but
because it's *load-bearing*: each one exists to make a single score true.

**Relax — ceremony that only matters when convincing strangers:**

- **The 5-gate QC pipeline → 2 gates.** Keep: verifier fails on base state
  (the reverse check, 2 minutes, catches a shocking fraction of broken
  tasks) + one valid-alternative solution (the acceptance-breadth check —
  the single highest-value QC step, and cheap: write the fix differently
  once). Cut: formal calibration (0/33/66/100 solutions — 4 extra
  solutions' work per task), the formal hack report, multi-stage review.
  Instead: one adversarial *attempt*, and trust your own read of one
  failing rollout when something looks off.
- **Anti-contamination discipline → weakened.** The contamination question
  only matters if you compare your pi results against published numbers on
  public benchmarks. You won't — you compare models against each other on
  *your* tasks. "Written from scratch" still helps (recall-free tasks
  discriminate better), but adapting a real PR or a session artifact is
  fine when it's convenient. The adversarial tier still matters — not as
  anti-cheat, but because memorized happy paths are where model differences
  actually show.
- **Quality rubrics and blockers.** FrontierCode needs them because it
  measures mergeability across subjective axes. If your tasks are
  behavioral (they are), per-test pass/fail weighted by tier is enough.
  Adopt rubrics later only if you build a task where "correct but ugly"
  genuinely differs from "correct."
- **Cross-version comparability and score stability.** v1.1's discipline
  exists so a public leaderboard stays comparable across benchmark updates.
  Yours just needs today's run to be true.
- **Repo diversity, language quotas, ≥500-star sourcing rules.** Pick
  whatever code is at hand — your own repos and session transcripts are
  ideal.

**Keep — these make one score true:**

- **Determinism.** Non-negotiable even solo. A flaky verifier turns model
  comparison into astrology and costs you hours of confused debugging.
  (We watched a wall-clock TTL test flip in real time on this machine.)
- **Behavioral verification + no gold in the environment.** This is the
  entire validity of the benchmark. If the agent can find the answer, or
  the verifier grades structure instead of behavior, every score is a lie.
- **Separate verifier environment + per-test structured report.** The
  two mechanisms that stop gaming-by-omission (deleted tests, early exits,
  monkey-patched frameworks) — cheap in Harbor (one task.toml line and a
  CTRF emitter) and they're why you can trust a surprising pass.
- **Prompt↔verifier bijection.** Costs one extra read-through at authoring
  time; saves you from grading a task you didn't state. The cheapest
  high-value discipline in this guide.
- **No wall-clock as a metric.** DeepSWE v1.1 dropped it entirely — host
  load and provider queues make it noise. Track tokens and cost; let
  wall-clock be trivia.
- **The regression suite.** Leaving the rest of the codebase working is
  half the task; without it you're rewarding agents that burn the repo to
  ship the feature.

## 11. Checklist for a new task

- [ ] One capability, discoverable from real work (session/issue/standard)
- [ ] Sized 20–60 min for a strong agent; difficulty from subtlety, not bulk
- [ ] Novel: no public solution exists to recall
- [ ] `instruction.md`: short, natural, symptom+requirements, includes repo
      conventions, says nothing about tests/grading, states every graded
      requirement
- [ ] Multi-part requirements stated explicitly (they're a feature)
- [ ] Environment: base state reproducible, shallow git with no future
      history, everything vendored, works with `no-network`, no gold anywhere
- [ ] Verifier: behavioral (public interfaces only), bijective with the
      prompt, regression suite included, deterministic across 3 runs,
      per-test structured report, tiers with adversarial cases
- [ ] Reverse check: verifier fails on the base state
- [ ] Hack report: adversarial solution fails; alternative-structure
      solution passes
- [ ] Calibration: 0/33/66/100 solutions score as expected
- [ ] `task.toml`: `network_mode = "no-network"`,
      `verifier.environment_mode = "separate"`, honest timeouts and resources
- [ ] Reviewed by someone who didn't write it, including one failing
      rollout inspected end-to-end
