import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
describe("README documents single-ownership", () => {
  test("does not describe thinking pinning as part of fixed-defaults", () => {
    const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");
    expect(readme).not.toContain("pins the current model and thinking level");
    expect(readme).toContain("pins only the cross-session provider and model");
    expect(readme).toContain("sole owner");
  });
  test("documents the provider/model-only JSON shape", () => {
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
});
