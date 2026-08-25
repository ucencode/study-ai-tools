import { useEffect, useState } from "react";

const KEY = "study-tools-theme";

// "auto" is the absence of a choice, not a third palette: it removes the attribute
// and lets `color-scheme: light dark` follow the OS, which is what styles.css does
// with no JS at all.
export const THEMES = ["auto", "light", "dark"];

function stored() {
  try {
    const value = localStorage.getItem(KEY);
    return THEMES.includes(value) ? value : "auto";
  } catch {
    // Storage can be refused outright (private windows, blocked site data). The
    // app still themes correctly, it just won't remember across reloads.
    return "auto";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState(stored);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);

    try {
      localStorage.setItem(KEY, theme);
    } catch {
      // See above: not remembering is survivable, throwing here is not.
    }
  }, [theme]);

  return [theme, setTheme];
}
