import { create } from "zustand";

type AppState = {
  activeCountry: string;
  setActiveCountry: (country: string) => void;
};

export const useAppStore = create<AppState>((set) => ({
  activeCountry: "MX",
  setActiveCountry: (activeCountry) => set({ activeCountry }),
}));
