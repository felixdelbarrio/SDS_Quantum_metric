import { create } from "zustand";
import { persist } from "zustand/middleware";

type AppState = {
  activeCountry: string;
  hasCountryPreference: boolean;
  setActiveCountry: (country: string) => void;
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeCountry: "MX",
      hasCountryPreference: false,
      setActiveCountry: (activeCountry) =>
        set({ activeCountry, hasCountryPreference: true }),
    }),
    {
      name: "sds-quantum-dashboard-preferences",
      partialize: (state) => ({
        activeCountry: state.activeCountry,
        hasCountryPreference: state.hasCountryPreference,
      }),
    },
  ),
);
