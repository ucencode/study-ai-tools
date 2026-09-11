import { useEffect, useRef, useState } from "react";

import { CURRICULUM, createCurriculumJob, createQuiz, modelsForRole } from "../api.js";
import { fileSize, languageLabel } from "../format.js";
import { INLINE_ERROR, INLINE_WARNING, MUTED, PRIMARY, QUIET, ROW, SECONDARY_BUTTON } from "../styles.js";
import PresetBar from "./PresetBar.jsx";
import Quiz from "./Quiz.jsx";
import Wizard from "./Wizard.jsx";

const FORM = "flex flex-col gap-3.5 max-w-[780px]";

// Left empty on purpose: `source_name` is what the reader asked this job to be called,
// and an empty one lets `jobLabel` fall back to the course the metadata stage extracts.
const TITLE_PLACEHOLDER = "Title (optional)";

// The file is read here and sent as text, so anything the browser can decode works.
// The check exists to stop a PDF filling the box with binary, not to police extensions.
const TEXT_FILE = /\.(txt|md|markdown|text|csv|json|ya?ml)$/i;

export default function CurriculumForm({ config, models, ollamaDown, configError, onRetryMeta, onSubmitted }) {
  const [curriculum, setCurriculum] = useState("");
  const [title, setTitle] = useState("");
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("short");
  const [lang, setLang] = useState("auto");
  const [includePlan, setIncludePlan] = useState(true);
  // Which step is live. Everything before it shows its answer, everything after it is a
  // dimmed preview.
  const [step, setStep] = useState(0);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [missingModel, setMissingModel] = useState(null);
  // { name, size } of the file the syllabus came from, or null when it was typed.
  const [source, setSource] = useState(null);
  const [dragging, setDragging] = useState(false);
  // Set when the reader picks "write it out instead" — the box alone is the default.
  const [manual, setManual] = useState(false);
  // A preset has answered every step after the syllabus, whenever it was applied.
  const [preset, setPreset] = useState(false);
  const picker = useRef(null);

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
    setPreset(true);
    // A preset answers every step but the syllabus, so there is nothing left to walk
    // through: jump to the end, or wait on the one question it cannot answer — which
    // `leaveSource` then continues straight to the end.
    setStep(curriculum.trim() ? steps.length - 1 : 0);
  }

  /** Leaving the syllabus step. Everything after it is a settings question, so a preset
      that was applied first has already answered all of them. */
  function leaveSource() {
    setStep(preset ? steps.length - 1 : 1);
  }

  /** The one way the syllabus changes. `from` is the file it was read out of, or null
      when it was typed — and either way the quiz is retired, because those questions
      were written from the text that was there when they were generated. */
  function setSyllabus(text, from) {
    setCurriculum(text);
    setSource(from);
    setQuestions([]);
    setAnswers([]);
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
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(withQuiz) {
    setBusy(true);
    setError(null);
    try {
      const job = await createCurriculumJob({
        curriculum,
        model,
        source_name: title.trim(),
        lang,
        mode,
        include_plan: includePlan,
        questions: withQuiz ? questions : [],
        answers: withQuiz ? answers : [],
      });
      onSubmitted([job], true);
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Load a syllabus from disk, however it arrived: dropped on the box or picked. */
  function readFile(file) {
    if (!file) return;
    if (!TEXT_FILE.test(file.name) && !file.type.startsWith("text/")) {
      setError(`${file.name} is not a text file — paste the syllabus instead.`);
      return;
    }
    file.text().then(
      (text) => {
        setSyllabus(text, { name: file.name, size: file.size });
        // The filename is the obvious title, and it is still editable above.
        setTitle(file.name.replace(/\.[^.]+$/, ""));
        setError(null);
        // The file is the whole answer to this step, so don't make them press Continue.
        leaveSource();
      },
      (e) => setError(String(e)),
    );
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
  const selectedLanguage = config.languages.find((option) => option.value === lang);
  const lines = curriculum.trim() ? curriculum.trim().split("\n").length : 0;

  // The syllabus is either loaded or typed; the editor appears once there is something
  // to look at, and the box stands alone until then.
  const editing = manual || curriculum.length > 0;

  const steps = [
    {
      id: "source",
      title: "Curriculum",
      hint: editing
        ? "Name it if you like, then continue."
        : "Drop a syllabus file on the box, choose one, or write it out instead.",
      complete: curriculum.trim().length > 0,
      summary: `${title.trim() || "Untitled"} · ${lines} line${lines === 1 ? "" : "s"}`,
      // Nothing to continue with while the box is the only thing on screen: a file
      // moves the step on by itself, and typing is what brings the button back.
      action: editing ? undefined : null,
      onContinue: leaveSource,
      body: (
        // One drop target over the whole step: dropping a file on a textarea otherwise
        // makes the browser navigate to it.
        <div
          className="flex flex-col gap-3"
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            readFile(event.dataTransfer.files?.[0]);
          }}
        >
          {editing ? (
            <>
              {source && (
                <ul className={`rounded-md border ${dragging ? "border-accent" : "border-line"}`}>
                  <li className="flex items-center gap-2 px-3 py-2 text-sm">
                    <span className="font-medium [overflow-wrap:anywhere]">{source.name}</span>
                    <span className={MUTED}>· {fileSize(source.size)}</span>
                    <button
                      type="button"
                      className="ml-auto px-1 border-0 bg-transparent text-muted hover:text-fg"
                      aria-label={`Remove ${source.name}`}
                      onClick={() => {
                        setSyllabus("", null);
                        // The title came from this filename, so it goes with it.
                        setTitle("");
                        setManual(false);
                        setError(null);
                      }}
                    >
                      ×
                    </button>
                  </li>
                </ul>
              )}

              <label className="field field-wide">
                <span>Title</span>
                <input
                  type="text"
                  value={title}
                  placeholder={TITLE_PLACEHOLDER}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>

              <label className="field field-wide">
                <span>Syllabus</span>
                <textarea
                  rows={10}
                  value={curriculum}
                  placeholder="Paste or write the syllabus here."
                  // Editing keeps the file it came from; emptying the box drops it, so a
                  // row never points at a file with nothing under it.
                  onChange={(event) =>
                    setSyllabus(event.target.value, event.target.value ? source : null)
                  }
                />
              </label>

              {curriculum.length === 0 && (
                <div className={ROW}>
                  <button type="button" className={QUIET} onClick={() => setManual(false)}>
                    Use a file instead
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <button
                type="button"
                className={`flex flex-col items-center gap-1 px-3.5 py-6.5 border-[1.5px] border-dashed
                            rounded-md text-sm ${
                  dragging ? "border-accent bg-accent-weak" : "border-line bg-transparent hover:border-accent hover:bg-accent-weak"
                }`}
                onClick={() => picker.current?.click()}
              >
                <span>Drop a syllabus file here, or click to choose</span>
                <span className={MUTED}>TXT · MD · max one file</span>
              </button>

              <div className={ROW}>
                <button type="button" className={QUIET} onClick={() => setManual(true)}>
                  Write the syllabus out instead
                </button>
              </div>
            </>
          )}

          <input
            ref={picker}
            type="file"
            accept=".txt,.md,.markdown,.text,.csv,.json,.yaml,.yml,text/*"
            hidden
            onChange={(event) => {
              readFile(event.target.files?.[0]);
              // Cleared so re-picking the file that was just removed still fires a change.
              event.target.value = "";
            }}
          />
        </div>
      ),
    },
    {
      id: "depth",
      title: "Depth",
      hint: "How much the textbook writes, and whether the plan travels with it.",
      complete: Boolean(mode),
      // The green is the only colour in a summary line: whether the plan reaches the
      // document is the one answer here that is easy to leave wrong by accident.
      summary: (
        <>
          {selectedMode?.label ?? mode} ·{" "}
          {includePlan ? (
            <span className="text-ok">self-plan included</span>
          ) : (
            "self-plan not included"
          )}
        </>
      ),
      body: (
        <>
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

          <label className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-sm">
            <input
              type="checkbox"
              className="mt-[3px]"
              checked={includePlan}
              onChange={(event) => setIncludePlan(event.target.checked)}
            />
            <span>Include the study plan in the document</span>
          </label>
        </>
      ),
    },
    {
      id: "model",
      title: "Model",
      hint: "Every stage of this job runs on it.",
      complete: Boolean(model),
      summary: `${model} · ${selectedLanguage ? languageLabel(selectedLanguage) : lang}`,
      body: (
        <>
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
            <span>Language</span>
            <select value={lang} onChange={(event) => setLang(event.target.value)}>
              {config.languages.map((option) => (
                <option key={option.value} value={option.value}>
                  {languageLabel(option)}
                </option>
              ))}
            </select>
          </label>
        </>
      ),
    },
    {
      id: "calibration",
      title: "Calibration",
      hint: "Optional: answer a few questions so the material can skip what you know.",
      complete: true,
      body: questions.length > 0 && (
        <Quiz
          questions={questions}
          answers={answers}
          onAnswer={answer}
          onBack={() => setQuestions([])}
          onStart={() => submit(true)}
          busy={busy}
        />
      ),
      // The quiz brings its own buttons; before it exists, this step is the choice
      // between asking for one and starting without it.
      action:
        questions.length > 0 ? null : (
          <div className={ROW}>
            <button type="button" className={PRIMARY} disabled={!ready || busy} onClick={loadQuiz}>
              {busy ? "Working…" : "Generate calibration quiz"}
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
        ),
    },
  ];

  return (
    <div className={FORM}>
      <h2 className="text-base font-semibold">Curriculum generator</h2>
      <p className={MUTED}>
        Turn a syllabus into a study plan and a textbook, one step at a time.
      </p>

      <PresetBar service={CURRICULUM} settings={settings} onApply={applySettings} />

      {missingModel && (
        <p className={INLINE_WARNING}>
          ⚠ That preset asks for {missingModel}, which is not installed. The current
          selection was kept.
        </p>
      )}

      <Wizard steps={steps} current={step} onCurrent={setStep} />

      {error && <p className={INLINE_ERROR}>{error}</p>}
    </div>
  );
}
