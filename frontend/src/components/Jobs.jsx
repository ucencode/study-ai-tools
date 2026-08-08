import { useCallback, useEffect, useState } from "react";
import { cancelJob, deleteJob, downloadUrl, listJobs } from "../api";
import { TERMINAL_STATUSES, useStream } from "../useStream";
import StreamPanel from "./StreamPanel";

const POLL_MS = 3000;

const TOOL_LABEL = {
  "study-plan-generatinator": "Study Plan",
  "slide-summarizinator": "Slides",
};

function age(iso) {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h${String(minutes % 60).padStart(2, "0")}m ago`
                    : `${Math.floor(hours / 24)}d ago`;
}

export default function Jobs() {
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const stream = useStream();

  const refresh = useCallback(async () => {
    try {
      const body = await listJobs();
      setJobs(body.jobs);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  // the list has no push channel of its own — a running job's progress only
  // shows up on the next poll
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  function watch(job) {
    setSelected(job.id);
    stream.attach(job.id);
  }

  async function onCancel(job) {
    try {
      await cancelJob(job.id);
    } catch (e) {
      setError(e.message);
    }
    refresh();
  }

  async function onDelete(job) {
    try {
      await deleteJob(job.id);
      if (selected === job.id) {
        setSelected(null);
        stream.reset();
      }
    } catch (e) {
      setError(e.message);
    }
    refresh();
  }

  return (
    <div className="layout">
      <section className="panel controls">
        <h2>Jobs</h2>
        <p className="hint">
          Every run happens on the server. Closing the tab, reloading, or switching
          machines never stops one — attach to a job to watch it from the beginning.
        </p>

        {error && <p className="error">{error}</p>}
        {jobs.length === 0 && <p className="empty">Nothing has been run yet.</p>}

        <ul className="jobs">
          {jobs.map((job) => (
            <li key={job.id} className={`job${selected === job.id ? " active" : ""}`}>
              <div className="job-head">
                <span className={`pill pill-${job.status}`}>{job.status}</span>
                <strong className="ellipsis">{TOOL_LABEL[job.tool] ?? job.tool}</strong>
                <span className="muted">{age(job.created_at)}</span>
              </div>

              <p className="muted ellipsis job-label">{job.label || job.id}</p>

              {job.progress && job.progress.total > 1 && (
                <span className="progress" title={`${job.progress.completed} of ${job.progress.total}`}>
                  <span className="progress-bar"
                        style={{ width: `${Math.round((job.progress.completed / job.progress.total) * 100)}%` }} />
                  <span className="progress-label">
                    {job.progress.completed}/{job.progress.total}
                  </span>
                </span>
              )}

              {job.error && <p className="error small">{job.error}</p>}

              {job.results.length > 0 && (
                <div className="results">
                  {job.results.map((result) => (
                    <a key={result.path} href={downloadUrl(result.tool, result.name)}
                       download className="result">
                      <span>{result.cached ? "reused" : "saved"}</span> {result.name}
                    </a>
                  ))}
                </div>
              )}

              <div className="row job-actions">
                <button type="button" className="ghost small" onClick={() => watch(job)}>
                  {selected === job.id ? "Reattach" : "Attach"}
                </button>
                {!TERMINAL_STATUSES.has(job.status) && (
                  <button type="button" className="ghost small" onClick={() => onCancel(job)}>
                    Cancel
                  </button>
                )}
                {TERMINAL_STATUSES.has(job.status) && (
                  <button type="button" className="ghost small" onClick={() => onDelete(job)}>
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <StreamPanel stream={stream}
                   emptyHint="Pick a job and hit Attach — its whole output replays, then follows live." />
    </div>
  );
}
