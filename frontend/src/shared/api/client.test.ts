import { describe, expect, it } from "vitest";

import { apiGet } from "./client";

describe("api client", () => {
  it("does not expose a Quantum Metric host in the frontend API base", () => {
    expect(apiGet.toString()).not.toContain("quantummetric.com");
  });
});
