# Hidden suite — 02-runtime-kernel-ownership

Held-out verifier tests. Never shipped into the agent's environment; injected
by `tests/test.sh` under their graded paths before the graded run.

**Status: not yet authored.** The hidden suite is written *with* the
reference implementation (the tests are the session's "Done means" contract
made executable; the reference must pass them and the base must fail them).
Until then this directory intentionally contains only this file.

## What the suite must prove (from the design session's "Done means")

Every item below becomes at least one named test that **fails on the curated
base and passes on the reference** (reverse-classical check enforced by
`gen_manifest.py`):

1. **Composition leaves the Telegram adapter** — `createTelegramIntake`
   receives a fully constructed lifecycle and dispatcher; constructing the
   bot no longer requires intake to build core runtime ownership; there is no
   nullable deferred-provider hookup left behind.
2. **A concrete runtime host owns the Surface-backed runtime state** —
   runner registration, runtime generation identity, captured Surface and
   skill fingerprints, in-flight construction identity, prompt queues, and
   disposal/quiescence all live behind the host's public contract.
3. **Invalidation semantics** — invalidation removes registration and queue
   state synchronously *before* asynchronous cleanup; concurrent creation
   cannot resurrect an invalidated runtime; the lifecycle-command queue is
   still preserved during a preference invalidation.
4. **Deployment lifetime** — `buildBot` no longer exposes mutable runner/
   queue maps; shutdown walks host-owned disposal (ordered, idempotent).
5. **Surface-free internal runtimes stay separate** — they are not
   disguised as Conversation runtimes.
6. **Dependency direction** — the runtime host does not import the
   dispatcher; lifecycle depends only on a narrow runtime contract; no
   import cycle remains among lifecycle, dispatcher, and the host.
7. **Regression** — the repo's own deterministic suite stays green (the
   full base suite minus the no-network exclusions, e.g. `src/voice.test.ts`,
   which calls the live edge-tts service).

## Authoring rules

- **Names must be new.** Hidden file basenames must not collide with any
  base test file (bun runs over an explicit file list; a collision would
  silently replace a graded regression file). Graded paths are
  repo-relative (bun runs from `/app`; junit `file` attributes are
  repo-relative), e.g. `src/orchestration/runtime-host.contract.test.ts`.
  Keep path entries in sync across `test.sh` (HIDDEN_TARGETS),
  `gen_manifest.py` (HIDDEN_FILES), and `calibrate.py` (graded_files).
- **Each hidden test name appears exactly once in its file.** The junit
  ledger keys are `file::line::name` (parametrized base tests legitimately
  repeat names at different lines), but a weighted hidden-test name must be
  unique or `gen_manifest.py` refuses the manifest.
- **Behavior first, structure only where the capability is structural.**
  Drive observable outcomes through public seams: the host's public
  contract, `createTelegramIntake`'s signature, `buildBot`'s return shape,
  shutdown ordering. The import-graph assertions (item 6) are the deliberate
  exception — this task's capability *is* module ownership — but keep them
  in one small "architecture boundary" tier, not scattered through
  behavioral tests.
- **Bijection.** Every hidden test corresponds to a requirement stated in
  `instruction.md`, and every stated requirement is tested. Write the pair
  in the same sitting.
- **Determinism.** No wall-clock assertions, no live network, no host
  state. The base suite already satisfies this for the graded file list;
  keep the new tests to the same standard (3 identical verifier runs).
- **No `mock.module`, no process-global mocks, no `mock.module`-style
  module replacement in hidden files.** bun applies module mocks to the
  whole `bun test` invocation, not just the registering file — verified
  2026-08-12: on tmpfs the mock leaks across files' processes and breaks
  unrelated suites (the subagents pi mock broke `agent/contract.test.ts`).
  The container overlay is expected to isolate like ext4, but that is
  unproven until the Docker smoke test; a hidden file is the worst place
  for the experiment. If a requirement seems to need a module mock,
  restructure the test to inject through the public seam instead.
- **Fake timers are fine on the pinned image.** `vi.useFakeTimers` exists
  in bun 1.3.7 but in no 1.2.x — that gap is why the image is pinned to
  1.3.7. Do not "fix" the pin to 1.2.x; it cannot run the base suite.