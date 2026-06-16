import { describe, expect, it } from "vitest";

const sourceFiles = import.meta.glob("../../**/*.{ts,tsx}", {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

describe("no video policy", () => {
  it("does not ship local session video affordances", () => {
    const payload = Object.entries(sourceFiles)
      .filter(([file]) => !file.endsWith("noVideoPolicy.test.ts"))
      .map(([, contents]) => contents)
      .join("\n");

    expect(payload).not.toMatch(/SessionVideo/u);
    expect(payload).not.toMatch(/play session/iu);
    expect(payload).not.toMatch(/\/video\b/iu);
  });
});
