import { describe, expect, test } from "bun:test";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import bundle from "./index.ts";

describe("bundle registration", () => {
  test("the entry point registers both ownership modules and no thinking listener", () => {
    const events = new Map<string, number>();
    const commands = new Set<string>();
    const providers = new Set<string>();

    // Proxy harness: records every registration call, no-ops the rest, and
    // gives the events channel a stub. This exercises the REAL bundle entry
    // point (index.ts) rather than importing the two modules directly.
    const api = new Proxy({} as ExtensionAPI, {
      get(_target, prop) {
        if (prop === "events") {
          return { on: () => () => {}, emit: () => {} };
        }
        if (prop === "on") {
          return (event: string) => {
            events.set(event, (events.get(event) ?? 0) + 1);
            return () => {};
          };
        }
        if (prop === "registerCommand") {
          return (name: string) => {
            commands.add(name);
          };
        }
        if (prop === "registerProvider") {
          return (id: string) => {
            providers.add(id);
          };
        }
        return () => {};
      },
    });

    bundle(api);

    expect(commands.has("fixed-defaults")).toBe(true);
    expect(commands.has("model-thinking")).toBe(true);
    expect(providers.has("kilo")).toBe(true);
    // Exactly one thinking_level_select listener remains in the bundle:
    // provider-balance's read-only footer tracking. The base bundle has two
    // (provider-balance + fixed-defaults' restoring listener); the split must
    // remove fixed-defaults'.
    expect(events.get("thinking_level_select") ?? 0).toBe(1);
    // both ownership modules still act on session start and model selection
    expect(events.get("session_start") ?? 0).toBeGreaterThanOrEqual(2);
    expect(events.get("model_select") ?? 0).toBeGreaterThanOrEqual(2);
  });
});
