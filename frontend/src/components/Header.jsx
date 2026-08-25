import { QUIET } from "../styles.js";
import { THEMES, useTheme } from "../useTheme.js";

// Health is three-valued: unknown is not the same as down, and must not look like it.
const GLYPH_COLOUR = { up: "text-ok", down: "text-warn", unknown: "text-muted" };

const THEME_LABEL = { auto: "Auto", light: "Light", dark: "Dark" };

function ThemeToggle() {
  const [theme, setTheme] = useTheme();

  return (
    <div
      className="flex items-center rounded-md border border-line overflow-hidden"
      role="group"
      aria-label="Colour theme"
    >
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          className={`px-2 py-0.5 text-xs border-0 ${
            theme === option
              ? "bg-accent-weak text-fg font-medium"
              : "bg-transparent text-muted hover:text-fg"
          }`}
          aria-pressed={theme === option}
          onClick={() => setTheme(option)}
        >
          {THEME_LABEL[option]}
        </button>
      ))}
    </div>
  );
}

export default function Header({ health, onRetry }) {
  const ollama = health?.ollama;
  const libreoffice = health?.libreoffice;

  return (
    <header className="bg-panel border-b border-line flex-none">
      <div className="flex items-center justify-between gap-4 px-4.5 py-3">
        <h1 className="text-xl font-semibold tracking-tight">Study Tools</h1>
        <div className="flex items-center gap-4 text-xs text-muted">
          <span>
            Ollama <span className={GLYPH_COLOUR[ollama || "unknown"]}>●</span>
          </span>
          <span>
            LibreOffice{" "}
            <span className={libreoffice ? "text-ok" : "text-warn"}>
              {libreoffice ? "✓" : "×"}
            </span>
          </span>
          <ThemeToggle />
        </div>
      </div>

      {ollama === "down" && (
        <div className="flex items-center justify-between gap-3 px-4.5 py-2 text-sm bg-warn-bg border-t border-warn-line text-warn">
          <span>Ollama is unavailable. New jobs cannot be submitted.</span>
          <button type="button" className={QUIET} onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
    </header>
  );
}
