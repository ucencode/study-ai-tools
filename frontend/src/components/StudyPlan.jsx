import { useEffect, useRef, useState } from "react";
import { postJSON } from "../api";
import { useStream } from "../useStream";
import StreamPanel from "./StreamPanel";

const MODE_HINT = {
  plan: "One streamed study plan.",
  full: "Plan, then material for every topic in a single pass.",
  book: "Plan, then one chained chapter per topic. Slow, but each finished chapter is "
      + "checkpointed — you can close the tab and resume.",
};

export default function StudyPlan({ config, models }) {
  const [curriculum, setCurriculum] = useState("");
  const [sourceName, setSourceName] = useState("curriculum.txt");
  const [model, setModel] = useState("");
  const [lang, setLang] = useState("auto");
  const [mode, setMode] = useState("plan");
  const [useCache, setUseCache] = useState(true);

  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [assessing, setAssessing] = useState(false);
  const [assessError, setAssessError] = useState(null);
  const [partial, setPartial] = useState(null);

  const stream = useStream();
  const running = stream.status === "running";
  const fileRef = useRef(null);

  useEffect(() => {
    if (!model && models.llm?.length) setModel(models.llm[0]);
  }, [models, model]);

  // book mode can pick up an interrupted run — ask the server if one exists
  useEffect(() => {
    if (mode !== "book" || !model || !sourceName) {
      setPartial(null);
      return undefined;
    }
    let cancelled = false;
    const query = new URLSearchParams({ source_name: sourceName, model, lang });
    fetch(`/api/study-plan/partial?${query}`)
      .then((r) => (r.ok ? r.json() : { partial: null }))
      .then((body) => !cancelled && setPartial(body.partial))
      .catch(() => !cancelled && setPartial(null));
    return () => { cancelled = true; };
  }, [mode, model, lang, sourceName]);

  function loadFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    file.text().then((text) => {
      setCurriculum(text);
      setSourceName(file.name);
      setQuestions([]);
      setAnswers({});
    });
  }

  async function runAssessment() {
    setAssessing(true);
    setAssessError(null);
    try {
      const body = await postJSON("/api/study-plan/assessment", { curriculum, model });
      setQuestions(body.questions);
      setAnswers(Object.fromEntries(body.questions.map((q) => [q.id, false])));
      if (!body.questions.length) {
        setAssessError("The model returned no usable questions — generating without an assessment.");
      }
    } catch (e) {
      setAssessError(e.message);
    } finally {
      setAssessing(false);
    }
  }

  function generate(fresh = false) {
    stream.start("/api/study-plan/stream", {
      curriculum,
      model,
      lang,
      mode,
      source_name: sourceName || "curriculum.txt",
      questions,
      answers: Object.entries(answers).map(([id, known]) => ({ id, known })),
      use_cache: useCache,
      fresh,
    });
  }

  const ready = curriculum.trim().length > 0 && model;

  return (
    <div className="layout">
      <section className="panel controls">
        <h2>Curriculum</h2>

        <label className="field">
          <span>Curriculum text</span>
          <textarea
            rows={12}
            value={curriculum}
            placeholder="Paste a syllabus, or load a .txt file…"
            onChange={(e) => setCurriculum(e.target.value)}
          />
        </label>

        <div className="row">
          <button type="button" className="ghost" onClick={() => fileRef.current?.click()}>
            Load .txt
          </button>
          <input ref={fileRef} type="file" accept=".txt,.md,text/plain"
                 onChange={loadFile} hidden />
          <span className="muted ellipsis">{sourceName}</span>
        </div>

        <div className="grid">
          <label className="field">
            <span>Model</span>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {(models.llm ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
              {!models.llm?.length && <option value="">no models found</option>}
            </select>
          </label>

          <label className="field">
            <span>Output language</span>
            <select value={lang} onChange={(e) => setLang(e.target.value)}>
              {config.languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.code} — {l.name}{l.experimental ? " *" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="field">
          <legend>Mode</legend>
          <div className="chips">
            {config.modes.map((m) => (
              <button
                key={m.value}
                type="button"
                className={`chip${mode === m.value ? " active" : ""}`}
                onClick={() => setMode(m.value)}
              >
                {m.label}
              </button>
            ))}
          </div>
          <p className="hint">{MODE_HINT[mode]}</p>
        </fieldset>

        {partial && (
          <p className="notice">
            An interrupted run is saved: {partial.completed}/{partial.total} chapters written.
            Generating will resume from chapter {partial.completed + 1}.
          </p>
        )}

        <label className="checkbox">
          <input type="checkbox" checked={useCache} onChange={(e) => setUseCache(e.target.checked)} />
          <span>Reuse a previous result for the same source, model, language and mode</span>
        </label>

        <h2>Familiarity check <span className="muted">(optional)</span></h2>
        <p className="hint">
          A few yes/no questions calibrate how deep the material goes — known topics get
          less hand-holding, unknown ones get more.
        </p>
        <button type="button" className="ghost" disabled={!ready || assessing || running}
                onClick={runAssessment}>
          {assessing ? "Generating questions…" : questions.length ? "Regenerate questions" : "Generate questions"}
        </button>
        {assessError && <p className="error">{assessError}</p>}

        {questions.length > 0 && (
          <ul className="questions">
            {questions.map((q) => (
              <li key={q.id}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={!!answers[q.id]}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.checked }))}
                  />
                  <span>
                    {q.question}
                    {q.topic && <em className="topic"> — {q.topic}</em>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <div className="row actions">
          <button type="button" className="primary" disabled={!ready || running}
                  onClick={() => generate(false)}>
            {running ? "Generating…" : "Generate"}
          </button>
          {mode === "book" && partial && (
            <button type="button" className="ghost" disabled={running}
                    onClick={() => generate(true)}>
              Start over
            </button>
          )}
        </div>
      </section>

      <StreamPanel stream={stream}
                   emptyHint="Paste a curriculum and hit Generate — the plan streams in as the model writes it." />
    </div>
  );
}
