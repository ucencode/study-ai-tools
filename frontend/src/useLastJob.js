import { useEffect } from "react";
import { getJob } from "./api";

/**
 * Remember the job a tool panel last submitted, and re-attach to it on mount.
 *
 * Jobs outlive the page, so a reload would otherwise leave a run going with
 * nothing watching it. The id is kept in localStorage per tool; on mount the
 * server is asked whether that job still exists, and if so the panel attaches
 * from event 0 — replaying the whole output, not just what happens next.
 */
export function useLastJob(key, stream) {
  const storageKey = `study-ai-tools:last-job:${key}`;

  useEffect(() => {
    const id = localStorage.getItem(storageKey);
    if (!id) return undefined;

    // `gone` guards the StrictMode double-mount: the first pass is discarded so
    // its attach never races the second one's
    let gone = false;
    getJob(id)
      .then((job) => { if (!gone) stream.attach(job.id); })
      .catch(() => localStorage.removeItem(storageKey)); // pruned or deleted
    return () => { gone = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  return (id) => {
    if (id) localStorage.setItem(storageKey, id);
    else localStorage.removeItem(storageKey);
  };
}
