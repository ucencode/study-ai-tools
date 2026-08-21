import { useEffect, useRef, useState } from "react";

import { createSlideJob, modelsForRole } from "../api.js";
import { fileSize, languageLabel } from "../format.js";

const MAX_BYTES = 200 * 1024 * 1024;

export default function SlidesForm({ config, models, ollamaDown, onSubmitted }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [action, setAction] = useState("summary");
  const [ocrModel, setOcrModel] = useState("");
  const [refineModel, setRefineModel] = useState("");
  const [lang, setLang] = useState("auto");
  const [level, setLevel] = useState("intermediate");
  const [dpi, setDpi] = useState(200);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const picker = useRef(null);

  const vision = modelsForRole(models, "vision");
  const refine = modelsForRole(models, "refine");
  const [firstVision, firstRefine] = [vision.options[0], refine.options[0]];

  useEffect(() => {
    if (!ocrModel && firstVision) setOcrModel(firstVision);
    if (!refineModel && firstRefine) setRefineModel(firstRefine);
  }, [ocrModel, refineModel, firstVision, firstRefine]);

  const pptxEnabled = config?.pptx_enabled;
  const refining = action !== "skip";
  const audienceApplies = action === "summary" || action === "deep";

  function choose(candidate) {
    setError(null);
    if (!candidate) return;
    const name = candidate.name.toLowerCase();
    const isPptx = name.endsWith(".pptx");
    if (!name.endsWith(".pdf") && !isPptx) {
      setError("Only .pdf and .pptx files are supported.");
      return;
    }
    if (isPptx && !pptxEnabled) {
      setError("LibreOffice is not installed, so .pptx cannot be converted.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError(`${fileSize(candidate.size)} exceeds the 200 MB limit.`);
      return;
    }
    setFile(candidate);
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return;

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

    setSubmitting(true);
    setError(null);
    try {
      onSubmitted(await createSlideJob(form));
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (!config) return <p className="empty">Loading configuration…</p>;

  const selectedAction = config.actions.find((option) => option.value === action);

  return (
    <form className="form" onSubmit={submit}>
      <h2 className="workspace-title">Slide summarizer</h2>
      <p className="secondary">
        OCR a slide deck page by page, then optionally refine it into a document.
      </p>

      {file ? (
        <div className="file-row">
          <span className="file-name">{file.name}</span>
          <span className="secondary">· {fileSize(file.size)} ·</span>
          <button type="button" className="quiet" onClick={() => picker.current?.click()}>
            Change file
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={`dropzone${dragging ? " dragging" : ""}`}
          onClick={() => picker.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files[0]);
          }}
        >
          <span>Drop a file here, or click to choose</span>
          <span className="secondary">
            PDF · <span className={pptxEnabled ? "" : "disabled-option"}>PPTX</span> · max 200 MB
          </span>
        </button>
      )}

      <input
        ref={picker}
        type="file"
        accept={pptxEnabled ? ".pdf,.pptx" : ".pdf"}
        hidden
        onChange={(event) => choose(event.target.files[0])}
      />

      {!pptxEnabled && (
        <p className="inline-warning">
          LibreOffice not installed — PPTX input unavailable. PDF still works.
        </p>
      )}

      <div className="fields">
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
            <span className="inline-warning">
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
          {selectedAction && <span className="secondary">{selectedAction.description}</span>}
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
              <span className="inline-warning">
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

      {error && <p className="inline-error">{error}</p>}

      <div className="row">
        <button
          type="submit"
          className="primary"
          disabled={!file || ollamaDown || submitting || !ocrModel}
        >
          {submitting ? "Submitting…" : "Start processing"}
        </button>
      </div>
    </form>
  );
}
