import { describe, expect, it } from "vitest";
import { cleanDisplayText } from "./displayText";

describe("cleanDisplayText", () => {
  it("removes Quantum pictograms without changing the label", () => {
    expect(cleanDisplayText("📄👀 Páginas Vistas")).toBe("Páginas Vistas");
    expect(cleanDisplayText("⚠️ Errores")).toBe("Errores");
  });
});
