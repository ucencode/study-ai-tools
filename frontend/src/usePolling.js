import { useCallback, useEffect, useRef, useState } from "react";

// The only polling primitive. Everything that watches the backend goes through here.
//
//   usePolling(fetcher, intervalMs, active) -> {data, error, stale, reconnected, lastUpdated, refresh}
//
// Rules it enforces so callers cannot get them wrong:
//   - `active` false means no requests at all. Terminal jobs pass false and stop.
//   - a tick is skipped while the previous request is still in flight.
//   - a failure keeps the last known data and marks it stale; polling continues.
//
// `fetcher` is read from a ref, so an inline arrow will not restart the interval.
// It also means a fetcher whose target changed keeps the *old* data until the next
// tick — mount the consumer with a `key` when the target can change.

const STALE_AFTER = 3; // consecutive failures before we admit the data is old
const RECONNECTED_MS = 3000;

export function usePolling(fetcher, intervalMs, active = true) {
  const latest = useRef(fetcher);
  latest.current = fetcher;

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [stale, setStale] = useState(false);
  const [reconnected, setReconnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const inFlight = useRef(false);
  const failures = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const next = await latest.current();
      if (!mounted.current) return;
      if (failures.current >= STALE_AFTER) setReconnected(true);
      failures.current = 0;
      setData(next);
      setError(null);
      setStale(false);
      setLastUpdated(Date.now());
    } catch (e) {
      if (!mounted.current) return;
      failures.current += 1;
      setError(e);
      if (failures.current >= STALE_AFTER) setStale(true);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    refresh();
    if (!intervalMs) return undefined;
    const timer = setInterval(refresh, intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs, refresh]);

  useEffect(() => {
    if (!reconnected) return undefined;
    const timer = setTimeout(() => setReconnected(false), RECONNECTED_MS);
    return () => clearTimeout(timer);
  }, [reconnected]);

  return { data, error, stale, reconnected, lastUpdated, refresh };
}
