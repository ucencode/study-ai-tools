import { useEffect, useState } from "react";
import { downloadUrl, getOutput, getOutputs } from "../api";

export default function Outputs() {
  const [outputs, setOutputs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { refresh(); }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const body = await getOutputs();
      setOutputs(body.outputs);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function open(entry) {
    setSelected(entry);
    setContent("");
    try {
      const body = await getOutput(entry.tool, entry.name);
      setContent(body.content);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="layout">
      <section className="panel controls">
        <div className="row spread">
          <h2>Saved outputs</h2>
          <button type="button" className="ghost" onClick={refresh} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {!loading && !outputs.length && <p className="empty">Nothing generated yet.</p>}

        <ul className="outputs">
          {outputs.map((entry) => (
            <li key={`${entry.tool}/${entry.name}`}>
              <button type="button"
                      className={`output${selected?.name === entry.name ? " active" : ""}`}
                      onClick={() => open(entry)}>
                <span className="output-name">{entry.name}</span>
                <span className="muted">
                  {entry.tool} · {entry.modified.replace("T", " ")} ·{" "}
                  {Math.max(1, Math.round(entry.size / 1024)).toLocaleString()} KB
                </span>
                {entry.meta?.course && <span className="tag">{entry.meta.course}</span>}
                {entry.meta?.mode && <span className="tag">{entry.meta.mode}</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel stream">
        <header className="stream-head">
          <div className="stream-title">
            <strong>{selected ? selected.name : "Preview"}</strong>
          </div>
          {selected && (
            <a className="ghost" href={downloadUrl(selected.tool, selected.name)} download>
              Download
            </a>
          )}
        </header>
        <div className="stream-body">
          {!selected && <p className="empty">Pick a file to read it here.</p>}
          {selected && <pre>{content || "Loading…"}</pre>}
        </div>
      </section>
    </div>
  );
}
