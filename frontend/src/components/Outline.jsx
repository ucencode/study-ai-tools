export default function Outline({ job }) {
  const outline = job.outline || [];
  if (outline.length === 0) return null;

  // Chapters are recorded by topic, so that is what identifies a written one.
  const written = new Map((job.chapters || []).map((chapter) => [chapter.topic, chapter]));

  return (
    <section className="panel-section">
      <div className="section-head">
        <h3 className="section-heading">Outline</h3>
        {written.size > 0 && (
          <p className="secondary">
            {written.size} of {outline.length} chapters written
          </p>
        )}
      </div>

      <ol className="outline">
        {outline.map((entry, index) => {
          const chapter = written.get(entry.topic);
          return (
            <li key={`${index}-${entry.topic}`} className={chapter ? "outline-written" : ""}>
              <span className="outline-number mono">{String(index + 1).padStart(2, "0")}</span>
              <div className="outline-body">
                <p className="outline-topic">
                  {chapter && <span className="glyph status-completed">✓</span>} {entry.topic}
                </p>
                {entry.scope && <p className="outline-scope">{entry.scope}</p>}
                {chapter?.established?.length > 0 && (
                  <details className="established">
                    <summary>Established terms ({chapter.established.length})</summary>
                    <p>{chapter.established.join(" · ")}</p>
                  </details>
                )}
              </div>
              <div className="outline-deps">
                <span className="label">Depends on</span>
                {entry.depends_on.length === 0 ? (
                  <span className="secondary">—</span>
                ) : (
                  entry.depends_on.map((topic) => (
                    <span key={topic} className="chip">
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
