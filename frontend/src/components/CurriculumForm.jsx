import { useEffect, useState } from "react";

import { CURRICULUM, createCurriculumJob, createQuiz, modelsForRole } from "../api.js";
import { languageLabel } from "../format.js";
import { INLINE_ERROR, INLINE_WARNING, MUTED, PRIMARY, QUIET, ROW, SECONDARY_BUTTON } from "../styles.js";
import PresetBar from "./PresetBar.jsx";
import Quiz from "./Quiz.jsx";

const FORM = "flex flex-col gap-3.5 max-w-[780px]";

const STEPS = [
  { id: "source", label: "Source" },
  { id: "calibration", label: "Calibration" },
  { id: "generate", label: "Generate" },
];

export default function CurriculumForm({ config, models, ollamaDown, configError, onRetryMeta, onSubmitted }) {
  const [curriculum, setCurriculum] = useState("");
  const [sourceName, setSourceName] = useState("curriculum.txt");
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("short");
  const [lang, setLang] = useState("auto");
  const [includePlan, setIncludePlan] = useState(true);
  const [step, setStep] = useState("source");
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [missingModel, setMissingModel] = useState(null);

  const { options: llmModels, fallback } = modelsForRole(models, "llm");
  const firstModel = llmModels[0];

  useEffect(() => {
    if (!model && firstModel) setModel(firstModel);
  }, [model, firstModel]);

  const ready = curriculum.trim().length > 0 && model && !ollamaDown;

  // What a preset stores: the form's own options, and nothing about the curriculum.
  const settings = { model, lang, mode, include_plan: includePlan };

  function applySettings(preset) {
    // A preset can name a model that is no longer installed — the catalogue is a hint,
    // not a whitelist. Keep the working selection and say so rather than submit nothing.
    const known = llmModels.includes(preset.model);
    if (known) setModel(preset.model);
    setMissingModel(known ? null : preset.model);
    setMode(preset.mode);
    setLang(preset.lang);
    setIncludePlan(preset.include_plan);
    setError(null);
  }

  async function loadQuiz() {
    setBusy(true);
    setError(null);
    try {
      const quiz = await createQuiz(curriculum, model);
      setQuestions(quiz.questions);
      // Deliberately empty: `known` is a boolean, so pre-filling it would submit an
      // answer the reader never gave. Skipping calibration is its own button.
      setAnswers([]);
      setStep("calibration");
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(withQuiz) {
    setBusy(true);
    setError(null);
    setStep("generate");
    try {
      const job = await createCurriculumJob({
        curriculum,
        model,
        source_name: sourceName,
        lang,
        mode,
        include_plan: includePlan,
        questions: withQuiz ? questions : [],
        answers: withQuiz ? answers : [],
      });
      onSubmitted([job], true);
    } catch (e) {
      setError(e.detail || String(e));
      setStep(withQuiz ? "calibration" : "source");
    } finally {
      setBusy(false);
    }
  }

  function readDroppedFile(event) {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    event.preventDefault();
    file.text().then((text) => {
      setCurriculum(text);
      setSourceName(file.name);
    });
  }

  function answer(id, known) {
    setAnswers((previous) => [
      ...previous.filter((entry) => entry.id !== id),
      { id, known },
    ]);
  }

  if (!config) {
    return configError ? (
      <div className={FORM}>
        <p className={INLINE_ERROR}>Configuration unavailable — {configError}</p>
        <div className={ROW}>
          <button type="button" className={SECONDARY_BUTTON} onClick={onRetryMeta}>
            Try again
          </button>
        </div>
      </div>
    ) : (
      <p className="text-sm text-muted">Loading configuration…</p>
    );
  }

  const selectedMode = config.modes.find((option) => option.value === mode);

  return (
    <div className={FORM}>
      <h2 className="text-base font-semibold">Curriculum generator</h2>

      <ol className="steps flex gap-3 text-xs text-muted">
        {STEPS.map((entry, index) => (
          <li key={entry.id} className={step === entry.id ? "text-fg font-medium" : ""}>
            <span className="font-mono">{index + 1}</span> {entry.label}
          </li>
        ))}
      </ol>

      <label className="field field-wide">
        <span>Curriculum</span>
        <textarea
          rows={12}
          value={curriculum}
          disabled={step === "calibration"}
          placeholder="Paste a syllabus, or drop a text file here."
          onChange={(event) => setCurriculum(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={readDroppedFile}
        />
        <span className={MUTED}>Source name · {sourceName}</span>
      </label>

      <PresetBar service={CURRICULUM} settings={settings} onApply={applySettings} />

      {missingModel && (
        <p className={INLINE_WARNING}>
          ⚠ That preset asks for {missingModel}, which is not installed. The current
          selection was kept.
        </p>
      )}

      <div className="flex flex-col gap-3">
        <label className="field">
          <span>Model</span>
          <select value={model} onChange={(event) => setModel(event.target.value)}>
            {llmModels.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {fallback && llmModels.length > 0 && (
            <span className={INLINE_WARNING}>
              ⚠ No installed model is marked <code>llm</code> in config/models.toml. Showing all
              models.
            </span>
          )}
        </label>

        <label className="field">
          <span>Mode</span>
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            {config.modes.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {selectedMode && <span className={MUTED}>{selectedMode.description}</span>}
        </label>

        <label className="field">
          <span>Language</span>
          <select value={lang} onChange={(event) => setLang(event.target.value)}>
            {config.languages.map((option) => (
              <option key={option.value} value={option.value}>
                {languageLabel(option)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-sm">
        <input
          type="checkbox"
          className="mt-[3px]"
          checked={includePlan}
          onChange={(event) => setIncludePlan(event.target.checked)}
        />
        <span>
          Include the study plan in the document
          <span className="block mt-0.5 text-xs text-muted">
            The study plan is generated either way. This controls only whether it appears in
            the final document.
          </span>
        </span>
      </label>

      {error && <p className={INLINE_ERROR}>{error}</p>}

      {step === "calibration" ? (
        <Quiz
          questions={questions}
          answers={answers}
          onAnswer={answer}
          onBack={() => setStep("source")}
          onStart={() => submit(true)}
          busy={busy}
        />
      ) : (
        <div className={ROW}>
          <button type="button" className={PRIMARY} disabled={!ready || busy} onClick={loadQuiz}>
            {busy ? "Working…" : "Continue to calibration"}
          </button>
          <button
            type="button"
            className={QUIET}
            disabled={!ready || busy}
            onClick={() => submit(false)}
          >
            Skip calibration and start
          </button>
        </div>
      )}
    </div>
  );
}
