import { MUTED } from "../styles.js";

const CHIP = "whitespace-nowrap border border-line rounded px-1.5 text-xs text-muted";

export default function Outline({ job }) {
  const outline = job.outline || [];
  if (outline.length === 0) return null;

  // Chapters are recorded by topic, so that is what identifies a written one.
  const written = new Map((job.chapters || []).map((chapter) => [chapter.topic, chapter]));

  return (
    <section className="panel-section">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">Outline</h3>
        {written.size > 0 && (
          <p className={MUTED}>
            {written.size} of {outline.length} chapters written
          </p>
        )}
      </div>

      <ol>
        {outline.map((entry, index) => {
          const chapter = written.get(entry.topic);
          return (
            <li
              key={`${index}-${entry.topic}`}
              className="grid grid-cols-[26px_minmax(0,1fr)_auto] gap-3 items-start py-2.5
                         border-t border-line max-rail:grid-cols-[26px_minmax(0,1fr)]"
            >
              <span className="text-xs text-muted font-mono">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <p className={`text-sm ${chapter ? "font-medium" : ""}`}>
                  {chapter && <span className="text-ok">✓</span>} {entry.topic}
                </p>
                {entry.scope && <p className="mt-0.5 text-xs text-muted">{entry.scope}</p>}
                {chapter?.established?.length > 0 && (
                  <details className="mt-1 text-xs text-muted">
                    <summary className="cursor-pointer">
                      Established terms ({chapter.established.length})
                    </summary>
                    <p className="mt-1">{chapter.established.join(" · ")}</p>
                  </details>
                )}
              </div>
              <div
                className="flex flex-wrap gap-1.5 items-baseline justify-end w-[320px]
                           max-rail:col-start-2 max-rail:w-auto max-rail:justify-start"
              >
                <span className="text-xs text-muted">Depends on</span>
                {entry.depends_on.length === 0 ? (
                  <span className={MUTED}>—</span>
                ) : (
                  entry.depends_on.map((topic) => (
                    <span key={topic} className={CHIP}>
                      {topic}
                    </span>
                  ))
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
