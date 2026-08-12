import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
describe("README documents single-ownership", () => {
  const readme = readFileSync(join(import.meta.dir, "README.md"), "utf8");

  test("fixed-defaults is described as pinning provider/model only", () => {
    // The stale dual-ownership claim must be gone.
    expect(readme).not.toContain("pins the current model and thinking level");

    // Accept either provider/model order and reasonable wording, but require
    // an explicit boundary around thinking ownership rather than just a list
    // of unrelated keywords somewhere in the README.
    expect(readme).toMatch(
      /fixed-defaults[\s\S]{0,240}(?:provider[\s\S]{0,80}model|model[\s\S]{0,80}provider)/i,
    );
    expect(readme).toMatch(
      /(?:fixed-defaults[\s\S]{0,240}(?:pins?\s+only|only\s+pins?|(?:provider[\s\S]{0,100}model|model[\s\S]{0,100}provider)[\s\S]{0,100}(?:only|sole|exclusive)|does not control thinking|doesn't control thinking|(?:does not|doesn't|never|no longer)\s+(?:control|pin|manage|own|set|persist)\s+thinking|model-thinking[\s\S]{0,100}(?:sole|owns?))|(?:only|sole|exclusive)[\s\S]{0,100}fixed-defaults)/i,
    );
  });

  test("shows the provider/model-only JSON shape", () => {
    expect(readme).toContain('"provider":');
    expect(readme).toContain('"model":');
    expect(readme).not.toContain("defaultThinkingLevel");
  });

  test("documents the legacy thinkingLevel migration", () => {
    expect(readme).toMatch(
      /(?:thinkingLevel[\s\S]{0,300}(?:ignored|not used|not applied|has no effect)|(?:ignored|not used|not applied|has no effect)[\s\S]{0,300}thinkingLevel)/i,
    );
    expect(readme).toContain("model-thinking.json");
  });

  test("explains that a hand-created pin applies from the next fresh session", () => {
    const pinAction = /(?:hand[- ]?(?:create|edit)(?:d|ing)?|manually\s+(?:create|edit)|(?:create|edit)(?:d|ing)?\s+(?:a\s+)?pin)/i;
    const laterSession = /\b(?:next|following|subsequent|fresh|new)\s+(?:new\s+)?session\b|\bsession\s+restart\b|\brestart(?:ing)?\s+(?:the\s+)?session\b/i;
    const hasNearbyTiming = new RegExp(
      `(?:${pinAction.source})[\\s\\S]{0,320}(?:${laterSession.source})|(?:${laterSession.source})[\\s\\S]{0,320}(?:${pinAction.source})`,
      "i",
    );
    expect(readme).toMatch(hasNearbyTiming);
  });
});
