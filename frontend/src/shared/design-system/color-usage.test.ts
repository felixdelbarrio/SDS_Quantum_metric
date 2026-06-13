import { describe, expect, it } from "vitest";

const colorLiteralPattern = /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/iu;
const sourceFiles = import.meta.glob("../../**/*.{css,ts,tsx}", {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

describe("design-system colors", () => {
  it("keeps color literals centralized in tokens.css", () => {
    const offenders = Object.entries(sourceFiles)
      .filter(([file]) => !file.endsWith(".test.ts"))
      .filter(([file]) => !file.endsWith(".test.tsx"))
      .filter(([file]) => !file.endsWith("tokens.css"))
      .filter(([, contents]) => colorLiteralPattern.test(contents))
      .map(([file]) => file);

    expect(offenders).toEqual([]);
  });
});
