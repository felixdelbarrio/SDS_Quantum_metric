import { Moon, Sun } from "lucide-react";
import { useAppStore } from "../state/appStore";
import { useThemeState } from "./themeState";

export function ThemeToggle() {
  const setThemePreference = useAppStore((state) => state.setThemePreference);
  const { resolvedTheme } = useThemeState();
  const nextTheme = resolvedTheme === "dark" ? "light" : "dark";
  const Icon = resolvedTheme === "dark" ? Sun : Moon;
  const label =
    nextTheme === "dark" ? "Cambiar a tema oscuro" : "Cambiar a tema claro";

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={label}
      title={label}
      onClick={() => setThemePreference(nextTheme)}
    >
      <Icon aria-hidden="true" size={18} />
    </button>
  );
}
