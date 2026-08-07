import { useCallback, useRef, useState } from "react";
import { streamSSE } from "./api";

/**
 * Consume a pipeline SSE stream into render-ready state.
 *
 * Tokens arrive faster than React should re-render, so they're accumulated in a
 * ref and flushed once per animation frame. That keeps the typing effect smooth
 * on long generations instead of queueing thousands of renders.
 */
export function useStream() {
  const [sections, setSections] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | running | done | error
  const [error, setError] = useState(null);
  const [results, setResults] = useState([]);
  const [progress, setProgress] = useState(null);

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
          setStatus("error");
          break;

        default:
          break;
      }
    },
    [flushNow, scheduleFlush],
  );

  const start = useCallback(
    async (path, body) => {
      reset();
      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("running");

      let failed = false;
      try {
        await streamSSE(path, { body, signal: controller.signal, onEvent: handleEvent });
      } catch (e) {
        if (e.name === "AbortError") {
          flushNow();
          setStatus("idle");
          return;
        }
        failed = true;
        setError(e.message);
        setStatus("error");
      } finally {
        abortRef.current = null;
        flushNow();
      }
      // an `error` frame already moved us to "error"; don't overwrite it
      if (!failed) setStatus((prev) => (prev === "error" ? prev : "done"));
    },
    [flushNow, handleEvent, reset],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { sections, statuses, status, error, results, progress, start, stop, reset };
}
