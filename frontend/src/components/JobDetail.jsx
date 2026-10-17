import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  CURRICULUM,
  SERVICE_LABEL,
  SLIDES,
  deleteJob,
  getJob,
  getRaw,
  retryJob,
} from "../api.js";
import { clockTime, duration, relativeTime } from "../format.js";
import { MUTED, SECONDARY_BUTTON } from "../styles.js";
import { useDocumentTitle } from "../useDocumentTitle.js";
import { usePolling } from "../usePolling.js";
import Outline from "./Outline.jsx";
import Output from "./Output.jsx";
import Stages, {
  STATUS_COLOUR,
  STATUS_GLYPH,
  STATUS_LABEL,
  isTerminal,
  jobLabel,
  statusLine,
  tabTitle,
} from "./Stages.jsx";

// Deleting a job destroys its output for good, so it reads as destructive rather than
// as the quiet link it sat next to. Inline, not in styles.js: this is the only place a
// button is destructive, and three shared button levels is the budget there.
const DESTRUCTIVE =
  "h-9 px-3.5 rounded-md text-sm font-medium bg-transparent border border-line text-fail " +
  "not-disabled:hover:border-fail not-disabled:hover:bg-fail/[7%]";

// Retry means different things per pipeline, and the copy must not lie about it.
function retryCopy(job) {
  if (job.service !== CURRICULUM) return "Re-runs this job from the beginning.";
  const written = job.chapters?.length || 0;
  if (written > 0) {
    return `Resumes from chapter ${written + 1} — finished chapters are kept.`;
  }
  if (job.outline?.length) {
    return "Resumes after the outline — metadata, plan and outline are kept.";
  }
  return "Resumes from the last finished stage — finished work is kept.";
}

// Summary and deep leave two documents behind — the OCR transcript and the result — and
// both are worth reading, so they get a tab each. Only the visible tab is mounted, so
// only one of them polls.
function hasTranscriptTab(job) {
  return job.service === SLIDES && ["summary", "deep"].includes(job.params?.action);
}

function SlideOutput({ job }) {
  const ocrRunning = job.status !== "completed" && job.status !== "failed" &&
    job.progress?.stage !== "refine";
  // Picked once when the job is opened and never switched for the reader afterwards,
  // so the view does not jump while someone is reading the transcript.
  const [tab, setTab] = useState(() => (ocrRunning ? "ocr" : "result"));
  const resultLabel = job.params.action === "deep" ? "Deep" : "Summary";

  const tabs = (
    <div role="tablist" className="flex gap-1">
      {[["ocr", "OCR"], ["result", resultLabel]].map(([key, text]) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={tab === key}
          onClick={() => setTab(key)}
          className={
            "px-2.5 py-1 rounded-md text-sm font-semibold border " +
            (tab === key
              ? "border-line bg-canvas text-fg"
              : "border-transparent bg-transparent text-muted hover:text-fg")
          }
        >
          {text}
        </button>
      ))}
    </div>
  );

  return tab === "ocr" ? (
    <Output key="ocr" job={job} fetch={getRaw} extension=".txt" heading={tabs} />
  ) : (
    <Output
      key="result"
      job={job}
      heading={tabs}
      empty={ocrRunning ? "Starts after OCR finishes." : undefined}
    />
  );
}

export default function JobDetail({ id, service, onDeleted }) {
  const fetcher = useCallback(() => getJob(service, id), [service, id]);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);

  // Polling stops the moment the job is terminal: the interval drops to 0, which
  // costs one final fetch and then no further requests.
  const [pollInterval, setPollInterval] = useState(1500);
  const polling = usePolling(fetcher, pollInterval, true);
  const job = polling.data;

  useDocumentTitle(job ? tabTitle(job) : null);

  const status = job?.status;
  useEffect(() => {
    setPollInterval(isTerminal(status) ? 0 : 1500);
    // A race note ("already resumed") is obsolete once the job settles again.
    if (isTerminal(status)) setNote(null);
  }, [status]);

  if (!job) {
    return (
      <p className="text-sm text-muted">
        {polling.error ? String(polling.error.detail) : "Loading job…"}
      </p>
    );
  }

  const terminal = isTerminal(job.status);
  const label = jobLabel(job);
  const ran = duration(job.started_at, job.finished_at);

  async function act(kind) {
    setBusy(true);
    setNote(null);
    try {
      if (kind === "delete") {
        await deleteJob(job.service, job.id);
        onDeleted(job.id);
        return;
      }
      await retryJob(job.service, job.id);
      polling.refresh();
    } catch (e) {
      // 409 is a race, not an error: the job went live between render and click.
      if (e instanceof ApiError && e.status === 409) {
        setNote(
          kind === "delete"
            ? "Job started processing before it could be deleted."
            : "This job has already resumed.",
        );
      } else {
        setNote(e.detail || String(e));
      }
      polling.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="flex flex-col">
      <header className="grid gap-1">
        <h2 className="text-xl font-semibold tracking-tight [overflow-wrap:anywhere]">{label}</h2>
        <p className={`text-sm ${STATUS_COLOUR[job.status]}`}>
          <span className={MUTED}>{SERVICE_LABEL[job.service]} · </span>
          <span>{STATUS_GLYPH[job.status]}</span> {STATUS_LABEL[job.status]}
          {job.status === "processing" && <span className={MUTED}> · {statusLine(job)}</span>}
        </p>
        <div className="flex flex-wrap gap-3.5 text-xs text-muted mt-0.5">
          <span className="text-xs font-mono">{job.id}</span>
          <span>Created {clockTime(job.created_at)}</span>
          {job.started_at && <span>Started {clockTime(job.started_at)}</span>}
          {job.finished_at && <span>Finished {clockTime(job.finished_at)}</span>}
          {ran && <span>Took {ran}</span>}
        </div>
        {polling.stale && (
          <p className="text-xs text-warn">
            Last updated {relativeTime(polling.lastUpdated)} · connection unavailable
          </p>
        )}
        {polling.reconnected && <p className="text-xs text-ok">Connected</p>}
      </header>

      <section className="panel-section">
        <Stages job={job} />
      </section>

      {job.error && (
        <section className="panel-section">
          <h3 className="text-sm font-semibold">Error</h3>
          <pre className="border border-fail border-l-[3px] rounded-md px-3 py-2.5 text-fail
            bg-fail/[7%] font-mono text-xs leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
            {job.error}
          </pre>
        </section>
      )}

      {terminal && (
        <section className="panel-section">
          <div className="flex items-center gap-2.5 flex-wrap mb-0.5">
            {job.status === "failed" && (
              <button
                type="button"
                className={SECONDARY_BUTTON}
                disabled={busy}
                onClick={() => act("retry")}
              >
                Retry job
              </button>
            )}
            <button
              type="button"
              className={DESTRUCTIVE}
              disabled={busy}
              onClick={() => act("delete")}
            >
              Delete job
            </button>
          </div>
          {job.status === "failed" && <p className={MUTED}>{retryCopy(job)}</p>}
          {note && <p className={MUTED}>{note}</p>}
        </section>
      )}

      {!terminal && note && <p className={MUTED}>{note}</p>}

      <Outline job={job} />
      {hasTranscriptTab(job) ? <SlideOutput job={job} /> : <Output job={job} />}
    </article>
  );
}
