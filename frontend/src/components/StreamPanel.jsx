import { useEffect, useRef, useState } from "react";
import { downloadUrl } from "../api";

/** Sticks the scroll container to the bottom, unless the reader scrolled up. */
function useStickyScroll(dep) {
  const ref = useRef(null);
  const stuck = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const onScroll = () => {
      stuck.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (el && stuck.current) el.scrollTop = el.scrollHeight;
  }, [dep]);

  return ref;
}

const STATUS_LABEL = {
  idle: "Idle",
  queued: "Queued",
  running: "Generating",
  done: "Finished",
  error: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

export default function StreamPanel({ stream, emptyHint }) {
  const { sections, statuses, status, error, results, progress, active } = stream;
  const [showLog, setShowLog] = useState(true);

  const total = sections.reduce((n, s) => n + s.text.length, 0);
  const bodyRef = useStickyScroll(total + sections.length);
  const logRef = useStickyScroll(statuses.length);
  const latest = statuses[statuses.length - 1];

  return (
    <section className="panel stream" aria-live="polite">
      <header className="stream-head">
        <div className="stream-title">
          <span className={`dot dot-${status}`} aria-hidden="true" />
          <strong>{STATUS_LABEL[status] ?? status}</strong>
          {total > 0 && <span className="muted"> · {total.toLocaleString()} chars</span>}
        </div>
        <div className="stream-actions">
          {progress && progress.total > 1 && (
            <span className="progress" title={`${progress.completed} of ${progress.total}`}>
              <span className="progress-bar"
                    style={{ width: `${Math.round((progress.completed / progress.total) * 100)}%` }} />
              <span className="progress-label">{progress.completed}/{progress.total}</span>
            </span>
          )}
          {active && (
            <>
              <button type="button" className="ghost" onClick={stream.detach}
                      title="Stop watching — the job keeps running">
                Detach
              </button>
              <button type="button" className="ghost" onClick={stream.stop}>Stop</button>
            </>
          )}
          {!active && sections.length > 0 && (
            <button type="button" className="ghost" onClick={stream.reset}>Clear</button>
          )}
        </div>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      <div className="stream-body" ref={bodyRef}>
        {sections.length === 0 && !error && (
          <p className="empty">{emptyHint}</p>
        )}
        {sections.map((section, i) => (
          <article key={section.key} className="section">
            <h3>
              {section.label}
              {section.restored && <span className="tag">restored</span>}
            </h3>
            <pre>
              {section.text}
              {active && i === sections.length - 1 && <span className="caret" />}
            </pre>
          </article>
        ))}
      </div>

      {results.length > 0 && (
        <div className="results">
          {results.map((result) => (
            <a key={result.path} href={downloadUrl(result.tool, result.name)}
               download className="result">
              <span>{result.cached ? "reused" : "saved"}</span> {result.name}
            </a>
          ))}
        </div>
      )}

      <div className="log-wrap">
        <button type="button" className="log-toggle" onClick={() => setShowLog((v) => !v)}
                aria-expanded={showLog}>
          {showLog ? "▾" : "▸"} activity
          {!showLog && latest && <span className="muted"> — {latest.message}</span>}
        </button>
        {showLog && (
          <div className="log" ref={logRef}>
            {statuses.length === 0 && <span className="muted">no activity yet</span>}
            {statuses.map((entry, i) => (
              <div key={i} className="log-line">
                {entry.stage && <span className="stage">[{entry.stage}]</span>} {entry.message}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
