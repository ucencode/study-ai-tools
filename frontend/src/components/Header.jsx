export default function Header({ health, onRetry }) {
  const ollama = health?.ollama;
  const libreoffice = health?.libreoffice;

  return (
    <header className="header">
      <div className="header-row">
        <h1 className="title">Study Tools</h1>
        <div className="health">
          <span className={`health-item health-${ollama || "unknown"}`}>
            Ollama <span className="glyph">●</span>
          </span>
          <span className={`health-item health-${libreoffice ? "up" : "down"}`}>
            LibreOffice <span className="glyph">{libreoffice ? "✓" : "×"}</span>
          </span>
        </div>
      </div>

      {ollama === "down" && (
        <div className="banner banner-warn">
          <span>Ollama is unavailable. New jobs cannot be submitted.</span>
          <button type="button" className="quiet" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
    </header>
  );
}
