import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemePreference = "system" | "light" | "dark";

type AppState = {
  activeCountry: string;
  hasCountryPreference: boolean;
  themePreference: ThemePreference;
  setActiveCountry: (country: string) => void;
  setThemePreference: (themePreference: ThemePreference) => void;
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeCountry: "MX",
      hasCountryPreference: false,
      themePreference: "system",
      setActiveCountry: (activeCountry) =>
        set({ activeCountry, hasCountryPreference: true }),
      setThemePreference: (themePreference) => set({ themePreference }),
    }),
    {
      name: "sds-quantum-dashboard-preferences",
      partialize: (state) => ({
        activeCountry: state.activeCountry,
        hasCountryPreference: state.hasCountryPreference,
        themePreference: state.themePreference,
      }),
    },
  ),
);
