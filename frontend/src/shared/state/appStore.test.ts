import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "./appStore";

const initialState = useAppStore.getInitialState();

describe("app store preferences", () => {
  beforeEach(() => {
    localStorage.clear();
    useAppStore.setState(initialState, true);
  });

  it("persists country and theme preference together", () => {
    useAppStore.getState().setActiveCountry("ES");
    useAppStore.getState().setThemePreference("dark");

    expect(useAppStore.getState().activeCountry).toBe("ES");
    expect(useAppStore.getState().themePreference).toBe("dark");

    const stored = JSON.parse(
      localStorage.getItem("sds-quantum-dashboard-preferences") ?? "{}",
    );
    expect(stored.state).toMatchObject({
      activeCountry: "ES",
      hasCountryPreference: true,
      themePreference: "dark",
    });
  });
});
