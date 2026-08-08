import { useEffect, useState } from "react";
import { getConfig, getHealth, getModels } from "./api";
import Jobs from "./components/Jobs";
import Outputs from "./components/Outputs";
import Slides from "./components/Slides";
import StudyPlan from "./components/StudyPlan";

const TABS = [
  { id: "plan", label: "Study Plan" },
  { id: "slides", label: "Slides" },
  { id: "jobs", label: "Jobs" },
  { id: "outputs", label: "Outputs" },
];

export default function App() {
  const [tab, setTab] = useState("plan");
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState({});
  const [health, setHealth] = useState(null);
  const [bootError, setBootError] = useState(null);

  useEffect(() => { boot(); }, []);

  async function boot() {
    setBootError(null);
    try {
      const [configBody, healthBody] = await Promise.all([getConfig(), getHealth()]);
      setConfig(configBody);
      setHealth(healthBody);
      if (healthBody.ollama === "up") setModels(await getModels());
    } catch (e) {
      setBootError(e.message);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true">◇</span>
          <div>
            <h1>study-ai-tools</h1>
            <p>PDFs and curricula into study material, on your own machine.</p>
          </div>
        </div>

        <div className="health">
          <span className={`dot dot-${health?.ollama === "up" ? "done" : "error"}`} aria-hidden="true" />
          Ollama {health?.ollama ?? "…"}
          <button type="button" className="ghost small" onClick={boot}>Recheck</button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((entry) => (
          <button key={entry.id} type="button" role="tab" aria-selected={tab === entry.id}
                  className={`tab${tab === entry.id ? " active" : ""}`}
                  onClick={() => setTab(entry.id)}>
            {entry.label}
          </button>
        ))}
      </nav>

      <main>
        {bootError && (
          <p className="error">
            Could not reach the API: {bootError}
          </p>
        )}
        {health?.ollama === "down" && (
          <p className="notice">
            Ollama isn’t reachable, so no models are listed. Start it with <code>ollama serve</code>,
            then hit Recheck.
          </p>
        )}
        {!config && !bootError && <p className="empty">Loading…</p>}

        {config && tab === "plan" && <StudyPlan config={config} models={models} />}
        {config && tab === "slides" && <Slides config={config} models={models} />}
        {config && tab === "jobs" && <Jobs />}
        {config && tab === "outputs" && <Outputs />}
      </main>
    </div>
  );
}
