# Make the Conversation runtime own its state

`little-goblin` is a Telegram-native personal agent (`bun`/TypeScript, strict).
The project is under an architecture-stabilization gate, and the accepted
ownership model is already documented in `ARCHITECTURE.md`: **Surface** owns
Telegram routing and preferences, **Conversation** owns durable history and
its immutable Execution Environment, the **Conversation runtime** owns
ephemeral runner/queue state, and **ConversationLifecycle** owns
authoritative binding transitions. Telegram intake is an adapter into those
modules — not their assembler.

The code does not yet express that. Three concrete mismatches:

1. **Composition is inverted.** `src/tg/intake.ts` constructs both the
   lifecycle and the dispatcher, wired through a null-guarded circular
   reference (`dispatcherRef`) that throws if the dispatcher is used before
   it exists. A Telegram adapter is acting as the application composition
   root.
2. **The "runtime host" is a facade, not an owner.** `src/orchestration/
   conversation-runtime-host.ts` merely forwards back into the ~1k-line
   `TurnDispatcher`, which actually owns the Surface-backed runtime maps and
   queues: runner registrations, runtime generation identity, captured
   Surface and skill fingerprints, in-flight construction identity, prompt
   queue state, and disposal/quiescence.
3. **`buildBot` hands out mutable runtime maps**, and `src/index.ts`
   shutdown manually iterates them; there is no single owner of runtime
   disposal for the deployment lifetime.

Fix it so the accepted ownership is physically true. The graded contract:

- **Composition happens before Telegram exists.** Construct the runtime
  host, Surface settings, lifecycle, and dispatcher, and only then hand them
  to `createTelegramIntake` — intake must receive them, not build them.
  Remove the deferred null-guarded hookup entirely.
- **The runtime host becomes the concrete owner** of the Surface-backed
  ephemeral runtime state listed above (registration, runtime generation
  identity, captured fingerprints, in-flight construction identity, prompt
  queues, disposal and quiescence). The dispatcher stops being the registry
  behind it. Invalidation removes registration and queue state
  **synchronously** before any asynchronous cleanup runs; concurrent
  creation cannot resurrect an invalidated runtime; the lifecycle-command
  queue is still preserved during a preference invalidation.
- **`buildBot` stops exposing mutable runner/queue maps**; shutdown walks
  host-owned disposal instead (idempotent, ordered).
- **Surface-free internal runtimes stay a separate concern** — do not
  disguise them as Conversation runtimes.
- **Remove the import cycle** among lifecycle, runtime host, and dispatcher.
  The runtime host must not import the dispatcher; lifecycle depends only on
  a narrow runtime contract.
- **Existing behavior is the contract**: binding transitions, creation
  races, queued-command ordering, delegated-work lifecycle, and disposal
  semantics must all remain intact. The existing test suite stays green.

Constraints — this cycle's scope is deliberately narrow:

- No `ConversationRuntimePlan`, no tool/capability redesign, no
  `AgentRunner` decomposition, no persistence or schema changes.
- No compatibility layer for the old construction API — migrate callers
  atomically.
- Keep the existing asynchronous authority checkpoints (binding re-checks
  across resolution, memory capture, registration). Do not collapse them
  into one early check.

## Repository conventions

- TypeScript strict; typecheck with `bun run typecheck` (`tsc --noEmit`).
- Tests: `bun test` from the repo root. `src/voice.test.ts` calls the live
  edge-tts service and cannot run offline — exclude it when self-verifying
  (`bun test --path-ignore-patterns=src/voice.test.ts`; the rest of the
  ~2,500-test suite is hermetic).
- Import direction: modules depend on narrow contracts, not on subsystem
  barrels; avoid import cycles (the orchestration cycle is the one you are
  removing).
- Read `ARCHITECTURE.md`, `BACKLOG.md`, and the `decisions/` records you
  touch; repository practice lives in `AGENTS.md`. The committed `BACKLOG`
  still names ACP as next — this accepted cycle supersedes that ordering for
  this change.
- Work on `main` at the base commit and commit your fix when done.