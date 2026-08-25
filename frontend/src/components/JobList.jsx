import { useEffect, useState } from "react";

import { SERVICE_LABEL, listJobs } from "../api.js";
import { relativeTime } from "../format.js";
import { QUIET } from "../styles.js";
import { usePolling } from "../usePolling.js";
import { STATUS_COLOUR, STATUS_GLYPH, statusLine } from "./Stages.jsx";

const GROUPS = [
  { key: "processing", heading: "Processing", match: (job) => job.status === "processing" },
  { key: "queued", heading: "Waiting", match: (job) => job.status === "queued" },
  {
    key: "recent",
    heading: "Recent",
    match: (job) => job.status === "completed" || job.status === "failed",
  },
];

const RAIL_HEADING = "text-xs font-semibold uppercase tracking-wider text-muted";

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
    // `data-open` only bites in the narrow layout, where the rail can be collapsed.
    <section
      data-open={open}
      className="group border-l border-line px-3 pt-3.5 pb-7 overflow-y-auto min-h-0
                 max-rail:overflow-y-visible max-rail:border-l-0 max-rail:border-t"
      aria-label="Jobs"
    >
      <div className="px-1 mb-2.5 max-rail:flex max-rail:items-baseline max-rail:gap-2.5">
        <h2 className={`${RAIL_HEADING} mb-0.5`}>Jobs</h2>
        <button
          type="button"
          className={`${QUIET} hidden max-rail:inline-block max-rail:ml-auto`}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"}
        </button>
        {/* One worker: at most one job runs, so "active" would imply parallelism. */}
        <p className="text-xs text-muted">
          {running} running · {waiting} waiting
        </p>
        {stale && (
          <p className="text-xs text-warn">
            Last updated {relativeTime(lastUpdated)} · connection unavailable
          </p>
        )}
        {reconnected && <p className="text-xs text-ok">Connected</p>}
      </div>

      {jobs.length === 0 && !stale && (
        <p className="text-sm text-muted max-rail:group-data-[open=false]:hidden">
          No jobs yet — submitted jobs appear here.
        </p>
      )}

      <div className="space-y-3.5 max-rail:group-data-[open=false]:hidden">
        {GROUPS.map(({ key, heading, match }) => {
          const group = jobs.filter(match);
          if (group.length === 0) return null;
          return (
            <div key={key}>
              <h3 className={`${RAIL_HEADING} px-2 pb-1`}>{heading}</h3>
              <ul>
                {group.map((job) => (
                  <li key={job.id}>
                    <button
                      type="button"
                      className={`grid gap-0.5 w-full text-left p-2 rounded-md border-0 text-inherit ${
                        job.id === activeJobId
                          ? "bg-panel shadow-[inset_2px_0_0_var(--accent)]"
                          : "bg-transparent hover:bg-panel"
                      }`}
                      aria-current={job.id === activeJobId ? "true" : undefined}
                      onClick={() => onSelect(job)}
                    >
                      <span className="text-xs uppercase tracking-wide text-muted">
                        {SERVICE_LABEL[job.service]}
                      </span>
                      <span className="text-sm [overflow-wrap:anywhere]">{labelOf(job)}</span>
                      <span className={`text-xs ${STATUS_COLOUR[job.status]}`}>
                        <span>{STATUS_GLYPH[job.status]}</span> {statusLine(job)}
                      </span>
                      <span className="text-xs text-muted">{relativeTime(job.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
