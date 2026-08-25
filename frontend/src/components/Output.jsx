import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { getOutput } from "../api.js";
import { clockTime } from "../format.js";
import { usePolling } from "../usePolling.js";
import { MUTED, QUIET } from "../styles.js";

const PINNED_SLACK = 40; // px from the bottom that still counts as "at the bottom"

export default function Output({ job }) {
  const running = job.status === "processing" || job.status === "queued";
  const fetcher = useCallback(() => getOutput(job.service, job.id), [job.service, job.id]);

  // A terminal job gets one final fetch and then no interval at all.
  const { data, stale, lastUpdated } = usePolling(fetcher, running ? 3000 : 0, true);

  const [copied, setCopied] = useState(false);
  const box = useRef(null);
  const pinned = useRef(true);
  const scrollTop = useRef(0);

  // The endpoint returns the whole file every time, so the content is replaced.
  // Keeping the reader where they were is the only thing that makes that bearable.
  const content = data?.content ?? "";

  function onScroll(event) {
    const el = event.currentTarget;
    scrollTop.current = el.scrollTop;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < PINNED_SLACK;
  }

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    if (running && pinned.current) el.scrollTop = el.scrollHeight;
    else el.scrollTop = scrollTop.current;
  }, [content, running]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="panel-section">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">Job output</h3>
        {content && (
          <button type="button" className={QUIET} onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>

      {job.status === "processing" && (
        <p className={MUTED}>
          Updating while the job runs
          {lastUpdated && !stale && <> · last update {clockTime(lastUpdated)}</>}
          {stale && <> · connection unavailable</>}
        </p>
      )}

      {content ? (
        <div
          className="max-h-[55vh] overflow-auto border border-line rounded-md bg-canvas px-3.5 py-3"
          ref={box}
          onScroll={onScroll}
        >
          <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
            {content}
          </pre>
        </div>
      ) : (
        <p className="text-sm text-muted">
          {running ? "Nothing written yet." : "This job produced no output."}
        </p>
      )}
    </section>
  );
}
