import { useState } from "react";
import { readRukhTheme, saveRukhTheme, type RukhTheme } from "../lib/theme";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<RukhTheme>(() => readRukhTheme());
  const nextTheme: RukhTheme = theme === "dark" ? "light" : "dark";
  const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      className="rukh-theme-toggle"
      type="button"
      aria-label={label}
      aria-pressed={theme === "dark"}
      title={label}
      onClick={() => {
        saveRukhTheme(nextTheme);
        setTheme(nextTheme);
      }}
    >
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
        {theme === "dark"
          ? <path d="M10 2.5v1.7m0 11.6v1.7M2.5 10h1.7m11.6 0h1.7M4.7 4.7l1.2 1.2m8.2 8.2 1.2 1.2m0-10.6-1.2 1.2m-8.2 8.2-1.2 1.2M13.8 10a3.8 3.8 0 1 1-7.6 0 3.8 3.8 0 0 1 7.6 0Z" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round"/>
          : <path d="M16.4 12.1A6.8 6.8 0 0 1 7.9 3.6a6.9 6.9 0 1 0 8.5 8.5Z" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round"/>}
      </svg>
      <span className="rukh-theme-toggle-label">{theme === "dark" ? "Dark" : "Light"}</span>
    </button>
  );
}
