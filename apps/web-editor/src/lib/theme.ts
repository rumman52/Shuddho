export type RukhTheme = "light" | "dark";

const STORAGE_KEY = "rukh-ai-theme:v1";

function storedTheme(): RukhTheme | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): RukhTheme {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

export function applyRukhTheme(theme: RukhTheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.rukhTheme = theme;
  root.style.colorScheme = theme;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = theme === "dark" ? "#171916" : "#F7F7F5";
}

export function readRukhTheme(): RukhTheme {
  if (typeof document !== "undefined") {
    const current = document.documentElement.dataset.rukhTheme;
    if (current === "light" || current === "dark") return current;
  }
  return storedTheme() ?? systemTheme();
}

export function initializeRukhTheme(): RukhTheme {
  const theme = storedTheme() ?? systemTheme();
  applyRukhTheme(theme);
  return theme;
}

export function saveRukhTheme(theme: RukhTheme): void {
  applyRukhTheme(theme);
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Theme still applies for this session when storage is unavailable.
  }
}
