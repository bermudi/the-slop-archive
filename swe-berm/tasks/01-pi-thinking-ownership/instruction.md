# Fix startup-model pinning in bermudis-pi-goodies

`bermudis-pi-goodies` is a pi extension bundle at `pi-packages/bermudis-pi-goodies`. It currently has a bug: two extensions both own "thinking level".

- `fixed-defaults` pins the persisted startup thinking level to `max`
- `model-thinking` sets the active thinking level (e.g. DeepSeek to `high`)

On a new session pi loads the startup value (`max`), then `model-thinking` overrides the active session to `high`, then `fixed-defaults` restores the startup file to `max` for next time. The current session ends up `high` while the saved setting is `max` — confusing dual ownership.

Your task is to make the ownership unambiguous:

1. `model-thinking` becomes the **sole owner** of thinking levels. It already does this — keep it that way and make it robust (malformed config should be reported and ignored, not treated as empty; `set` should not overwrite a broken file).
2. `fixed-defaults` must pin **only** the startup provider/model. Remove thinking-level handling from its config, file validation, commands, and event handling. A legacy `thinkingLevel` field in an existing `fixed-defaults.json` should be accepted for compatibility but ignored (warn once, don't fail).
3. Update the bundle's documentation so it no longer describes thinking-level pinning as part of `fixed-defaults` and documents the migration.
4. Keep the existing test suite green. The only expected failing test in the base is the wall-clock-dependent cache-TTL test — do not try to fix host-state reads.

## Constraints

- Do not merge the two files. The bundle is one pi extension; the modules stay separate and their registration order is deterministic.
- Provider and model remain a coupled pair — a file with only one of them is still invalid.
- `/fixed-defaults set` should pin the current model and rewrite the file in the new provider/model-only format. `/fixed-defaults reset` should persist the current model as Pi's last selection before removing the pin.
- Verify with `bun test` in `pi-packages/bermudis-pi-goodies` and `tsc --noEmit` if available.

You are on `main` at the base commit (no future history). Work on this branch and commit your fix when done.
