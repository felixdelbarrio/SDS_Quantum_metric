import { PropsWithChildren, useEffect } from "react";
import { useThemeState } from "./themeState";

export function ThemeProvider({ children }: PropsWithChildren) {
  const { preference, resolvedTheme } = useThemeState();

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = preference;
  }, [preference, resolvedTheme]);

  return children;
}
