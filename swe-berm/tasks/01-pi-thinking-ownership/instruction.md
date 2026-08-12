# Fix startup-model pinning in bermudis-pi-goodies

`bermudis-pi-goodies` is a pi extension bundle at `pi-packages/bermudis-pi-goodies`. It currently has a bug: two extensions both own "thinking level".

- `fixed-defaults` pins the persisted startup thinking level to `max`
- `model-thinking` sets the active thinking level (e.g. DeepSeek to `high`)

On a new session pi loads the startup value (`max`), then `model-thinking` overrides the active session to `high`, then `fixed-defaults` restores the startup file to `max` for next time. The current session ends up `high` while the saved setting is `max` — confusing dual ownership.

Your task is to make the ownership unambiguous:

1. `model-thinking` becomes the **sole owner** of thinking levels. It already does this — keep it that way and make it robust: a malformed `model-thinking.json` is reported and ignored (never treated as an empty policy), `/model-thinking set` refuses to overwrite a broken file, and `/model-thinking` status reports the broken state. A config that failed to load is not remembered forever: after you repair `model-thinking.json`, the next reload applies it.
2. `fixed-defaults` must pin **only** the startup provider/model. Remove thinking-level handling from its config type, file validation, commands, and event handling:
   - `/fixed-defaults set` writes only `provider`/`model` (rewriting an existing file into that format).
   - `/fixed-defaults` (status) shows the pin and the active model and must not claim to control thinking.
   - A legacy `thinkingLevel` field in an existing `fixed-defaults.json` is accepted for compatibility but ignored — warn once (not on every read), don't fail, and point the user at `/model-thinking`, including in the status output.
3. Update the bundle's documentation so it no longer describes thinking-level pinning as part of `fixed-defaults`, shows the provider/model-only JSON shape, documents the legacy-field migration, and explains that a hand-created pin applies from the next fresh session.
4. Keep the existing test suite green. Run `bun test` in `pi-packages/bermudis-pi-goodies` and `tsc --noEmit` if available.

## Constraints

- Do not merge the two files. The bundle is one pi extension; the modules stay separate and their registration order is deterministic.
- Provider and model remain a coupled pair — a file with only one of them is still invalid.
- `/fixed-defaults reset` on a valid provider/model pin persists the current model as Pi's last selection, then removes the pin; with no active model it refuses to remove a valid pin. An invalid, legacy-only, or partial override file is inactive: reset removes it without changing Pi's saved model selection.

You are on `main` at the base commit (no future history). Work on this branch and commit your fix when done.
