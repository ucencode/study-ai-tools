import { useEffect, useRef, useState } from "react";

import { SLIDES, createSlideJob, modelsForRole } from "../api.js";
import { fileSize, languageLabel } from "../format.js";
import { INLINE_ERROR, INLINE_WARNING, MUTED, PRIMARY, QUIET, ROW, SECONDARY_BUTTON } from "../styles.js";
import PresetBar from "./PresetBar.jsx";
import Toast from "./Toast.jsx";

const MAX_BYTES = 200 * 1024 * 1024;

const FORM = "flex flex-col gap-3.5 max-w-[780px]";

// A staged deck is identified by its content, not its name: two files called
// lecture.pdf picked from different folders are two different decks.
const fingerprint = (file) => `${file.name}:${file.size}:${file.lastModified}`;

export default function SlidesForm({ config, models, ollamaDown, configError, onRetryMeta, onSubmitted }) {
  // One entry per staged deck: { key, file, status, error }. Every one becomes its own
  // job — the backend puts a single input.pdf in a job directory, so a batch is N jobs
  // sharing this form's settings, never one job with N inputs.
  const [files, setFiles] = useState([]);
  // { text, progress: [current, total] | null, tone }. A toast with no progress is
  // finished, and the effect below clears it.
  const [toast, setToast] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [action, setAction] = useState("summary");
  const [ocrModel, setOcrModel] = useState("");
  const [refineModel, setRefineModel] = useState("");
  const [lang, setLang] = useState("auto");
  const [level, setLevel] = useState("intermediate");
  const [dpi, setDpi] = useState(200);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [missingModels, setMissingModels] = useState([]);
  const picker = useRef(null);

  const vision = modelsForRole(models, "vision");
  const refine = modelsForRole(models, "refine");
  const [firstVision, firstRefine] = [vision.options[0], refine.options[0]];

  useEffect(() => {
    if (!ocrModel && firstVision) setOcrModel(firstVision);
    if (!refineModel && firstRefine) setRefineModel(firstRefine);
  }, [ocrModel, refineModel, firstVision, firstRefine]);

  useEffect(() => {
    if (!toast || toast.progress) return undefined;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const pptxEnabled = config?.pptx_enabled;
  const refining = action !== "skip";
  const audienceApplies = action === "summary" || action === "deep";

  // What a preset stores: the form's own state, and nothing about the decks.
  const settings = {
    dpi: Number(dpi) || 200,
    ocr_model: ocrModel,
    action,
    refine_model: refineModel || null,
    lang,
    level: level || null,
  };

  function applySettings(preset) {
    // A preset can name a model that is no longer installed — the catalogue is a hint,
    // not a whitelist. Keep the working selection and say so rather than submit nothing.
    const missing = [];
    const keep = (options, wanted, current) => {
      if (!wanted) return current;
      if (options.includes(wanted)) return wanted;
      missing.push(wanted);
      return current;
    };

    setOcrModel(keep(vision.options, preset.ocr_model, ocrModel));
    setRefineModel(keep(refine.options, preset.refine_model, refineModel));
    setAction(preset.action);
    setLang(preset.lang);
    setDpi(preset.dpi);
    if (preset.level) setLevel(preset.level);
    setMissingModels(missing);
    setError(null);
  }

  /** Why this file cannot be a job, or null. Checked at pick time so nothing that is
      certain to fail ever reaches the staged list. */
  function rejection(candidate) {
    const name = candidate.name.toLowerCase();
    const isPptx = name.endsWith(".pptx");
    if (!name.endsWith(".pdf") && !isPptx) return "only .pdf and .pptx are supported";
    if (isPptx && !pptxEnabled) return "LibreOffice is not installed, so .pptx cannot be converted";
    if (candidate.size > MAX_BYTES) return `${fileSize(candidate.size)} exceeds the 200 MB limit`;
    return null;
  }

  function add(list) {
    const incoming = Array.from(list || []);
    if (incoming.length === 0) return;

    const seen = new Set(files.map((entry) => fingerprint(entry.file)));
    const accepted = [];
    const skipped = [];

    for (const candidate of incoming) {
      const reason = rejection(candidate);
      if (reason) {
        skipped.push(`${candidate.name}: ${reason}`);
        continue;
      }
      if (seen.has(fingerprint(candidate))) {
        skipped.push(`${candidate.name}: already added`);
        continue;
      }
      seen.add(fingerprint(candidate));
      accepted.push({ key: crypto.randomUUID(), file: candidate, status: "pending", error: null });
    }

    if (accepted.length > 0) setFiles((previous) => [...previous, ...accepted]);
    setError(
      skipped.length > 0
        ? `${skipped.length} file${skipped.length > 1 ? "s" : ""} skipped — ${skipped.join("; ")}.`
        : null,
    );
  }

  function remove(key) {
    setFiles((previous) => previous.filter((entry) => entry.key !== key));
    setError(null);
  }

  function formFor(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("ocr_model", ocrModel);
    form.append("action", action);
    form.append("dpi", String(dpi));
    // Omitted rather than sent empty: the backend's defaults are None, and "" is not.
    if (refining) {
      form.append("refine_model", refineModel);
      form.append("lang", lang);
    }
    if (audienceApplies) form.append("level", level);
    return form;
  }

  async function submit(event) {
    event.preventDefault();
    if (files.length === 0) return;

    setSubmitting(true);
    setError(null);

    const created = [];
    const failed = [];
    const plural = files.length > 1 ? "files" : "file";
    const uploading = (index) => ({
      text: `Uploading ${index}/${files.length} ${plural}…`,
      progress: [index, files.length],
      tone: "info",
    });

    // Sequential on purpose. The worker is FIFO, so the order these are accepted in is
    // the order they run in — and N concurrent uploads of a 200 MB deck helps nobody.
    for (const [index, entry] of files.entries()) {
      setToast(uploading(index + 1));
      setFiles((previous) =>
        previous.map((row) => (row.key === entry.key ? { ...row, status: "uploading" } : row)),
      );
      try {
        created.push(await createSlideJob(formFor(entry.file)));
      } catch (e) {
        failed.push({ ...entry, status: "failed", error: e.detail || String(e) });
      }
    }

    // The ones that became jobs are gone from here; the rest stay staged, so pressing
    // the button again is the retry.
    setFiles(failed);
    setSubmitting(false);
    if (failed.length > 0) {
      setError(`${failed.length} of ${files.length} could not be submitted — see the list above.`);
    }
    setToast({
      text: failed.length
        ? `${created.length} queued · ${failed.length} failed`
        : `${created.length} job${created.length > 1 ? "s" : ""} queued`,
      progress: null,
      tone: failed.length ? "warn" : "ok",
    });
    onSubmitted(created, failed.length === 0 && created.length === 1);
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

  const selectedAction = config.actions.find((option) => option.value === action);
  const batch = files.length > 1;
  // The toast owns the count while uploading; two places saying it would only drift.
  const label = submitting ? "Submitting…" : batch ? `Start ${files.length} jobs` : "Start processing";

  return (
    <form className={FORM} onSubmit={submit}>
      <h2 className="text-base font-semibold">Slide summarizer</h2>
      <p className={MUTED}>
        OCR a slide deck page by page, then optionally refine it into a document. Add
        several decks to queue one job each, all with the settings below.
      </p>

      {/* Dropping adds, whether the list is empty or not — so the handlers sit out here
          rather than on the empty-state button. */}
      <div
        className="flex flex-col gap-2"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          add(event.dataTransfer.files);
        }}
      >
        {files.length === 0 ? (
          <button
            type="button"
            className={`flex flex-col items-center gap-1 px-3.5 py-6.5 border-[1.5px] border-dashed
                        rounded-md text-sm ${
              dragging ? "border-accent bg-accent-weak" : "border-line bg-transparent hover:border-accent hover:bg-accent-weak"
            }`}
            onClick={() => picker.current?.click()}
          >
            <span>Drop files here, or click to choose</span>
            <span className={MUTED}>
              PDF ·{" "}
              <span className={pptxEnabled ? "" : "text-line line-through"}>PPTX</span> · max 200 MB
              each
            </span>
          </button>
        ) : (
          <>
            <ul className={`rounded-md border ${dragging ? "border-accent" : "border-line"}`}>
              {files.map((entry, index) => (
                <li
                  key={entry.key}
                  className="flex items-center gap-2 px-3 py-2 text-sm border-t border-line first:border-t-0"
                >
                  <span className={`${MUTED} font-mono`}>{String(index + 1).padStart(2, "0")}</span>
                  <span className="font-medium [overflow-wrap:anywhere]">{entry.file.name}</span>
                  <span className={MUTED}>· {fileSize(entry.file.size)}</span>
                  {entry.status === "uploading" && (
                    <span className="text-xs text-processing">uploading…</span>
                  )}
                  {entry.status === "failed" && (
                    <span className="text-xs text-fail [overflow-wrap:anywhere]">
                      ✗ {entry.error}
                    </span>
                  )}
                  <button
                    type="button"
                    className="ml-auto px-1 border-0 bg-transparent text-muted not-disabled:hover:text-fg"
                    disabled={submitting}
                    aria-label={`Remove ${entry.file.name}`}
                    onClick={() => remove(entry.key)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <div className={ROW}>
              <button
                type="button"
                className={QUIET}
                disabled={submitting}
                onClick={() => picker.current?.click()}
              >
                Add more files
              </button>
              <button
                type="button"
                className={QUIET}
                disabled={submitting}
                onClick={() => {
                  setFiles([]);
                  setError(null);
                }}
              >
                Clear all
              </button>
            </div>
          </>
        )}
      </div>

      <input
        ref={picker}
        type="file"
        accept={pptxEnabled ? ".pdf,.pptx" : ".pdf"}
        multiple
        hidden
        onChange={(event) => {
          add(event.target.files);
          // Cleared so re-picking a file that was just removed still fires a change.
          event.target.value = "";
        }}
      />

      {!pptxEnabled && (
        <p className={INLINE_WARNING}>
          LibreOffice not installed — PPTX input unavailable. PDF still works.
        </p>
      )}

      <PresetBar service={SLIDES} settings={settings} onApply={applySettings} />

      {missingModels.length > 0 && (
        <p className={INLINE_WARNING}>
          ⚠ That preset asks for {missingModels.join(", ")}, which is not installed. The
          current selection was kept.
        </p>
      )}

      <div className="flex flex-col gap-3">
        <label className="field">
          <span>OCR model</span>
          <select value={ocrModel} onChange={(event) => setOcrModel(event.target.value)}>
            {vision.options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {vision.fallback && vision.options.length > 0 && (
            <span className={INLINE_WARNING}>
              ⚠ No installed model is marked <code>vision</code> in config/models.toml. Showing
              all models — pick one that actually supports images.
            </span>
          )}
        </label>

        <label className="field">
          <span>Action</span>
          <select value={action} onChange={(event) => setAction(event.target.value)}>
            {config.actions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {selectedAction && <span className={MUTED}>{selectedAction.description}</span>}
        </label>

        {refining && (
          <label className="field">
            <span>Refine model</span>
            <select value={refineModel} onChange={(event) => setRefineModel(event.target.value)}>
              {refine.options.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            {refine.fallback && refine.options.length > 0 && (
              <span className={INLINE_WARNING}>
                ⚠ No installed model is marked <code>refine</code> in config/models.toml. Showing
                all models.
              </span>
            )}
          </label>
        )}

        {refining && (
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
        )}

        {audienceApplies && (
          <label className="field">
            <span>Audience</span>
            <select value={level} onChange={(event) => setLevel(event.target.value)}>
              {config.audiences.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="field">
          <span>DPI</span>
          <input
            type="number"
            min="50"
            max="600"
            step="10"
            value={dpi}
            onChange={(event) => setDpi(event.target.value)}
          />
        </label>
      </div>

      {error && <p className={INLINE_ERROR}>{error}</p>}

      <div className={ROW}>
        <button
          type="submit"
          className={PRIMARY}
          disabled={files.length === 0 || ollamaDown || submitting || !ocrModel}
        >
          {label}
        </button>
        {batch && !submitting && (
          <span className={MUTED}>One job each, run one at a time in this order.</span>
        )}
      </div>

      {toast && <Toast text={toast.text} progress={toast.progress} tone={toast.tone} />}
    </form>
  );
}
