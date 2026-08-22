import { useEffect, useState } from "react";

import { SERVICE_LABEL, listJobs } from "../api.js";
import { relativeTime } from "../format.js";
import { usePolling } from "../usePolling.js";
import { STATUS_GLYPH, statusLine } from "./Stages.jsx";

const GROUPS = [
  { key: "processing", heading: "Processing", match: (job) => job.status === "processing" },
  { key: "queued", heading: "Waiting", match: (job) => job.status === "queued" },
  {
    key: "recent",
    heading: "Recent",
    match: (job) => job.status === "completed" || job.status === "failed",
  },
];

const labelOf = (job) => job.params.filename || job.params.source_name || job.id;

export default function JobList({ activeJobId, onSelect, refreshToken }) {
  // Only meaningful in the narrow layout, where the rail sits below the workspace.
  const [open, setOpen] = useState(true);
  // The rail keeps polling for the life of the app: jobs also arrive from the CLI.
  const { data, stale, reconnected, lastUpdated, refresh } = usePolling(listJobs, 5000, true);

  // A freshly submitted job should appear here immediately, not up to 5s later.
  useEffect(() => {
    refresh();
  }, [refreshToken, refresh]);

  const jobs = data || [];
  const running = jobs.filter((job) => job.status === "processing").length;
  const waiting = jobs.filter((job) => job.status === "queued").length;

  return (
    <section className={`jobs${open ? "" : " collapsed"}`} aria-label="Jobs">
      <div className="jobs-head">
        <h2 className="rail-heading">Jobs</h2>
        <button
          type="button"
          className="quiet rail-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"}
        </button>
        {/* One worker: at most one job runs, so "active" would imply parallelism. */}
        <p className="counts">
          {running} running · {waiting} waiting
        </p>
        {stale && (
          <p className="stale">
            Last updated {relativeTime(lastUpdated)} · connection unavailable
          </p>
        )}
        {reconnected && <p className="reconnected">Connected</p>}
      </div>

      {jobs.length === 0 && !stale && (
        <p className="empty">No jobs yet — submitted jobs appear here.</p>
      )}

      {GROUPS.map(({ key, heading, match }) => {
        const group = jobs.filter(match);
        if (group.length === 0) return null;
        return (
          <div key={key} className="job-group">
            <h3 className="group-heading">{heading}</h3>
            <ul>
              {group.map((job) => (
                <li key={job.id}>
                  <button
                    type="button"
                    className={`job-row${job.id === activeJobId ? " selected" : ""}`}
                    aria-current={job.id === activeJobId ? "true" : undefined}
                    onClick={() => onSelect(job)}
                  >
                    <span className="job-service">{SERVICE_LABEL[job.service]}</span>
                    <span className="job-label">{labelOf(job)}</span>
                    <span className={`job-status status-${job.status}`}>
                      <span className="glyph">{STATUS_GLYPH[job.status]}</span> {statusLine(job)}
                    </span>
                    <span className="job-time">{relativeTime(job.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
