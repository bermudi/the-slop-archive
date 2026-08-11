import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
describe("README documents single-ownership", () => {
  test("fixed-defaults is described as pinning provider/model only", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    // The stale dual-ownership claim must be gone.
    expect(readme).not.toContain("pins the current model and thinking level");
    // And the prose must say the pin covers the provider/model pair.
    expect(readme).toMatch(
      /fixed-defaults[^\n]{0,160}(provider[^\n]{0,60}model)/i,
    );
  });
  test("shows the provider/model-only JSON shape", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    expect(readme).toContain('"provider":');
    expect(readme).toContain('"model":');
    expect(readme).not.toContain("defaultThinkingLevel");
  });
  test("documents the legacy thinkingLevel migration", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    expect(readme).toMatch(/thinkingLevel[\s\S]{0,300}ignored/i);
    expect(readme).toContain("model-thinking.json");
  });
  test("explains that a hand-created pin applies from the next fresh session", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    expect(readme).toMatch(/fresh session/i);
  });
});
