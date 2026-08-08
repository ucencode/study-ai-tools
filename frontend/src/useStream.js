import { useCallback, useEffect, useRef, useState } from "react";
import { cancelJob, streamJob, submitJob } from "./api";

/**
 * Watch a background job and turn its event stream into render-ready state.
 *
 * A job outlives whoever is watching it, so this hook is a *spectator*: `start`
 * submits and attaches, `attach` re-attaches to an existing job (replaying it
 * from the beginning so a reloaded tab renders the whole document), `detach`
 * stops watching, and only `stop` actually kills the run.
 *
 * Tokens arrive faster than React should re-render, so they're accumulated in a
 * ref and flushed once per animation frame. That keeps the typing effect smooth
 * on long generations instead of queueing thousands of renders.
 */

const TERMINAL = new Set(["done", "error", "cancelled", "interrupted"]);

export function useStream() {
  const [sections, setSections] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | queued | running | done | error | cancelled | interrupted
  const [error, setError] = useState(null);
  const [results, setResults] = useState([]);
  const [progress, setProgress] = useState(null);
  const [jobId, setJobId] = useState(null);

  const abortRef = useRef(null);
  const pendingRef = useRef("");
  const frameRef = useRef(null);

  const applyPending = useCallback(() => {
    const text = pendingRef.current;
    pendingRef.current = "";
    if (!text) return;
    setSections((prev) => {
      if (!prev.length) return [{ key: "output", label: "Output", text }];
      const next = prev.slice();
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, text: last.text + text };
      return next;
    });
  }, []);

  const flushNow = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    applyPending();
  }, [applyPending]);

  const scheduleFlush = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      applyPending();
    });
  }, [applyPending]);

  const reset = useCallback(() => {
    flushNow();
    pendingRef.current = "";
    setSections([]);
    setStatuses([]);
    setResults([]);
    setProgress(null);
    setError(null);
    setStatus("idle");
    setJobId(null);
  }, [flushNow]);

  const handleEvent = useCallback(
    ({ type, data }) => {
      switch (type) {
        case "token":
          pendingRef.current += data.text ?? "";
          scheduleFlush();
          break;

        case "section":
          flushNow(); // land buffered text in the old section first
          setSections((prev) => [
            ...prev,
            { key: `${data.key}-${prev.length}`, label: data.label, text: "", restored: !!data.restored },
          ]);
          break;

        case "status":
          setStatuses((prev) => [...prev.slice(-199), { ...data, at: Date.now() }]);
          if (typeof data.total === "number" && typeof data.completed === "number") {
            setProgress({ completed: data.completed, total: data.total });
          } else if (typeof data.pages === "number" && typeof data.page === "number") {
            setProgress({ completed: data.page, total: data.pages });
          }
          break;

        case "done":
          flushNow();
          setResults((prev) => [...prev, data]);
          break;

        case "error":
          flushNow();
          setError(data.message ?? "generation failed");
          break;

        // the job record — the authority on what state the run is in
        case "job":
          flushNow();
          setJobId(data.id);
          setStatus(data.status);
          if (data.error) setError(data.error);
          if (data.progress) setProgress(data.progress);
          break;

        default:
          break;
      }
    },
    [flushNow, scheduleFlush],
  );

  /** Follow an existing job from `from`, replaying what it has already produced. */
  const attach = useCallback(
    async (id, { from = 0 } = {}) => {
      abortRef.current?.abort();
      reset();
      setJobId(id);
      setStatus("queued"); // the first `job` frame corrects this a round trip later

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamJob(id, { from, signal: controller.signal, onEvent: handleEvent });
      } catch (e) {
        if (e.name === "AbortError") return; // detached on purpose
        setError(e.message);
        setStatus("error");
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        flushNow();
      }
    },
    [flushNow, handleEvent, reset],
  );

  /** Submit a new job, then watch it. Returns the job id. */
  const start = useCallback(
    async (path, body) => {
      abortRef.current?.abort();
      reset();
      setStatus("queued");
      let job;
      try {
        job = await submitJob(path, body);
      } catch (e) {
        setError(e.message);
        setStatus("error");
        return null;
      }
      void attach(job.id); // deliberately not awaited — the caller wants the id now
      return job.id;
    },
    [attach, reset],
  );

  /** Stop watching. The job keeps running and can be reattached. */
  const detach = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  /** Actually kill the run. */
  const stop = useCallback(async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch (e) {
      setError(e.message);
    }
  }, [jobId]);

  // never leave a reader open behind an unmounting panel
  useEffect(() => () => abortRef.current?.abort(), []);

  const active = status !== "idle" && !TERMINAL.has(status);

  return { sections, statuses, status, error, results, progress, jobId, active,
           start, attach, detach, stop, reset };
}

export { TERMINAL as TERMINAL_STATUSES };
