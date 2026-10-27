import { useEffect, useState } from "react";

import { getSettings, saveSettings } from "../api.js";
import { INLINE_ERROR, INLINE_WARNING, MUTED, PRIMARY, QUIET, ROW, SECONDARY_BUTTON } from "../styles.js";

const FORM = "flex flex-col gap-3.5 max-w-[780px]";

// `codex login status` prints this when a ChatGPT or API-key login is stored.
const signedIn = (status) => Boolean(status) && status.startsWith("Logged in");

// A limit window as the plan states it: 300 → "5-hour", 43200 → "30-day".
function windowLabel(minutes) {
  if (!minutes) return "Usage";
  if (minutes % 1440 === 0) return `${minutes / 1440}-day`;
  if (minutes % 60 === 0) return `${minutes / 60}-hour`;
  return `${minutes}-minute`;
}

function UsageWindow({ window, reached }) {
  const used = Math.min(100, Math.max(0, window.used_percent));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span>{windowLabel(window.window_minutes)} limit</span>
        <span className="font-mono text-xs">{used}% used</span>
      </div>
      <div
        className="h-1.5 rounded-full bg-line overflow-hidden"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={used}
        aria-label={`${windowLabel(window.window_minutes)} limit used`}
      >
        <div className={`h-full ${reached ? "bg-fail" : "bg-accent"}`} style={{ width: `${used}%` }} />
      </div>
      {window.resets_at && (
        <span className={MUTED}>Resets {new Date(window.resets_at * 1000).toLocaleString()}</span>
      )}
    </div>
  );
}

export default function Settings({ onSaved }) {
  const [loaded, setLoaded] = useState(null);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);

  function show(data) {
    setLoaded(data);
    setEnabled(data.codex.enabled);
  }

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (cancelled) return;
        show(data);
        setError(null);
      })
      .catch((e) => !cancelled && setError(e.detail || String(e)));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      show(await saveSettings({ codex: { enabled } }));
      setSaved(true);
      onSaved();
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) {
    return error ? (
      <div className={FORM}>
        <p className={INLINE_ERROR}>Settings unavailable — {error}</p>
        <div className={ROW}>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      </div>
    ) : (
      <p className="text-sm text-muted">Loading settings…</p>
    );
  }

  const login = loaded.codex_login;
  const usage = loaded.codex_usage;

  return (
    <div className={FORM}>
      <h2 className="text-base font-semibold">Settings</h2>

      <section className="flex flex-col gap-3.5 rounded-md border border-line px-4 py-3.5">
        <div>
          <h3 className="text-sm font-semibold">OpenAI Codex</h3>
          <p className={MUTED}>
            Tip: Codex uses your ChatGPT subscription account, so it is not billed per token.
            Its models write slide summaries and deep documents, and every stage of the
            curriculum generator. OCR stays on Ollama.
          </p>
        </div>

        <div className="field">
          <span>Account</span>
          {login === null ? (
            <span className={INLINE_WARNING}>
              The codex CLI is not installed. Install it, then run <code>codex login</code> in a
              terminal.
            </span>
          ) : signedIn(login) ? (
            <span className="text-sm">{login}</span>
          ) : (
            <span className={INLINE_WARNING}>
              {login} — run <code>codex login</code> in a terminal, then reload this page.
            </span>
          )}
        </div>

        <div className="field">
          <span>Usage</span>
          {loaded.codex_usage_error ? (
            <pre className={`${INLINE_ERROR} font-mono text-xs whitespace-pre-wrap [overflow-wrap:anywhere]`}>
              {loaded.codex_usage_error}
            </pre>
          ) : (
            <div className="flex flex-col gap-2.5">
              <span className="text-sm">
                Plan: <span className="font-medium">{usage.plan ?? "unknown"}</span>
              </span>
              {usage.windows.map((window, index) => (
                <UsageWindow key={index} window={window} reached={Boolean(usage.limit_reached)} />
              ))}
              {usage.limit_reached && (
                <span className="text-sm text-fail">
                  Limit reached ({usage.limit_reached}). Codex jobs fail until it resets.
                </span>
              )}
              {usage.lifetime_tokens != null && (
                <span className={MUTED}>
                  {usage.lifetime_tokens.toLocaleString()} tokens used on this account in total
                </span>
              )}
            </div>
          )}
          <button
            type="button"
            className={`${QUIET} justify-self-start`}
            onClick={() => setAttempt((n) => n + 1)}
          >
            Refresh
          </button>
        </div>

        <label className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-sm">
          <input
            type="checkbox"
            className="mt-[3px]"
            checked={enabled}
            onChange={(event) => {
              setEnabled(event.target.checked);
              setSaved(false);
            }}
          />
          <span>Offer Codex models in the model lists</span>
        </label>

        <div className="field">
          <span>Models</span>
          {loaded.codex_models_error ? (
            // The raw error, as everywhere else: prettifying it would invent detail.
            <pre className={`${INLINE_ERROR} font-mono text-xs whitespace-pre-wrap [overflow-wrap:anywhere]`}>
              {loaded.codex_models_error}
            </pre>
          ) : loaded.codex_models.length === 0 ? (
            <span className={INLINE_WARNING}>Your account has no Codex models available.</span>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {loaded.codex_models.map((name) => (
                <li key={name} className="px-2 py-0.5 rounded-md border border-line font-mono text-xs">
                  codex/{name}
                </li>
              ))}
            </ul>
          )}
          <span className={MUTED}>
            What your plan allows, read from Codex. When switched on, these appear in the
            model lists. A reply arrives whole, so a chapter appears at once rather than
            growing.
          </span>
        </div>

        <div className={ROW}>
          <button type="button" className={PRIMARY} disabled={saving} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </button>
          {saved && <span className={MUTED}>Saved.</span>}
        </div>

        {error && <p className={INLINE_ERROR}>{error}</p>}
      </section>
    </div>
  );
}
