/**
 * A short-lived note in the corner. It exists because a batch upload is the one thing
 * in this app that takes a while but produces nothing to look at yet — the jobs only
 * reach the rail one at a time, as each upload is accepted.
 *
 * Counts, never a time estimate: decks vary too much to guess at.
 */
export default function Toast({ text, progress, tone = "info" }) {
  const [current, total] = progress || [];

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-5 right-5 z-50 w-[260px] rounded-md border bg-panel px-3.5 py-3
                  shadow-lg shadow-black/10 ${
        tone === "ok" ? "border-ok" : tone === "warn" ? "border-warn" : "border-line"
      }`}
    >
      <p className="text-sm">{text}</p>

      {progress && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-canvas">
          <div
            className="h-full bg-accent transition-[width] duration-200"
            style={{ width: `${total ? (current / total) * 100 : 0}%` }}
          />
        </div>
      )}
    </div>
  );
}
