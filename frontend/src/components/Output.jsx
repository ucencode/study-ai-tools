import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { getOutput } from "../api.js";
import { clockTime } from "../format.js";
import { usePolling } from "../usePolling.js";

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
      <div className="section-head">
        <h3 className="section-heading">Job output</h3>
        {content && (
          <button type="button" className="quiet" onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>

      {job.status === "processing" && (
        <p className="secondary">
          Updating while the job runs
          {lastUpdated && !stale && <> · last update {clockTime(lastUpdated)}</>}
          {stale && <> · connection unavailable</>}
        </p>
      )}

      {content ? (
        <div className="output" ref={box} onScroll={onScroll}>
          <pre>{content}</pre>
        </div>
      ) : (
        <p className="empty">
          {running ? "Nothing written yet." : "This job produced no output."}
        </p>
      )}
    </section>
  );
}
