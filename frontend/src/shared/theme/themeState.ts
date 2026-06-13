import { useEffect, useState } from "react";
import { ThemePreference, useAppStore } from "../state/appStore";

type ResolvedTheme = "light" | "dark";

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

export function useThemeState() {
  const preference = useAppStore((state) => state.themePreference);
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() =>
    getSystemTheme(),
  );

  useEffect(() => {
    const media = window.matchMedia(SYSTEM_DARK_QUERY);
    const update = () => setSystemTheme(media.matches ? "dark" : "light");
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return {
    preference,
    resolvedTheme: resolveTheme(preference, systemTheme),
  };
}

function resolveTheme(
  preference: ThemePreference,
  systemTheme: ResolvedTheme,
): ResolvedTheme {
  return preference === "system" ? systemTheme : preference;
}

function getSystemTheme(): ResolvedTheme {
  if (window.matchMedia(SYSTEM_DARK_QUERY).matches) {
    return "dark";
  }
  return "light";
}
