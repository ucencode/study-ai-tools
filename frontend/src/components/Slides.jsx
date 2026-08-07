import { useEffect, useRef, useState } from "react";
import { getInputs, uploadPdf } from "../api";
import { useStream } from "../useStream";
import StreamPanel from "./StreamPanel";

export default function Slides({ config, models }) {
  const [files, setFiles] = useState([]);
  const [file, setFile] = useState("");
  const [ocrModel, setOcrModel] = useState("");
  const [refineModel, setRefineModel] = useState("");
  const [action, setAction] = useState("skip");
  const [lang, setLang] = useState("auto");
  const [level, setLevel] = useState("intermediate");
  const [dpi, setDpi] = useState(200);
  const [useCache, setUseCache] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [dragging, setDragging] = useState(false);

  const stream = useStream();
  const running = stream.status === "running";
  const fileRef = useRef(null);

  useEffect(() => { refreshFiles(); }, []);

  useEffect(() => {
    if (!ocrModel && models.vision?.length) setOcrModel(models.vision[0]);
    if (!refineModel && models.refine?.length) setRefineModel(models.refine[0]);
  }, [models, ocrModel, refineModel]);

  async function refreshFiles(select) {
    try {
      const body = await getInputs();
      setFiles(body.files);
      setFile((current) => select ?? (current || body.files[0]?.name || ""));
    } catch {
      setFiles([]);
    }
  }

  async function upload(picked) {
    if (!picked) return;
    setUploading(true);
    setUploadError(null);
    try {
      const body = await uploadPdf(picked);
      await refreshFiles(body.name);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files?.[0]);
  }

  function generate() {
    stream.start("/api/slides/stream", {
      file,
      ocr_model: ocrModel,
      action,
      refine_model: action === "skip" ? null : refineModel,
      lang,
      level: action === "summary" || action === "deep" ? level : null,
      dpi: Number(dpi),
      use_cache: useCache,
    });
  }

  const needsRefineModel = action !== "skip";
  const ready = file && ocrModel && (!needsRefineModel || refineModel);

  return (
    <div className="layout">
      <section className="panel controls">
        <h2>Slides</h2>

        <div
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
        >
          {uploading ? "Uploading…" : "Drop a PDF here, or click to choose one"}
          <input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden
                 onChange={(e) => upload(e.target.files?.[0])} />
        </div>
        {uploadError && <p className="error">{uploadError}</p>}

        <label className="field">
          <span>PDF in inputs/</span>
          <select value={file} onChange={(e) => setFile(e.target.value)}>
            {files.map((f) => (
              <option key={f.name} value={f.name}>
                {f.name} ({Math.round(f.size / 1024).toLocaleString()} KB)
              </option>
            ))}
            {!files.length && <option value="">no PDFs yet</option>}
          </select>
        </label>

        <div className="grid">
          <label className="field">
            <span>Vision model (OCR)</span>
            <select value={ocrModel} onChange={(e) => setOcrModel(e.target.value)}>
              {(models.vision ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
              {!models.vision?.length && <option value="">no vision models found</option>}
            </select>
          </label>

          <label className="field">
            <span>Render DPI</span>
            <input type="number" min={50} max={600} step={25} value={dpi}
                   onChange={(e) => setDpi(e.target.value)} />
          </label>
        </div>

        <fieldset className="field">
          <legend>Refine mode</legend>
          <div className="chips">
            {config.actions.map((a) => (
              <button key={a.value} type="button"
                      className={`chip${action === a.value ? " active" : ""}`}
                      onClick={() => setAction(a.value)}>
                {a.label}
              </button>
            ))}
          </div>
          <p className="hint">
            {config.actions.find((a) => a.value === action)?.description}
          </p>
        </fieldset>

        {needsRefineModel && (
          <div className="grid">
            <label className="field">
              <span>Refine model</span>
              <select value={refineModel} onChange={(e) => setRefineModel(e.target.value)}>
                {(models.refine ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
                {!models.refine?.length && <option value="">no refine models found</option>}
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
        )}

        {(action === "summary" || action === "deep") && (
          <fieldset className="field">
            <legend>Audience level</legend>
            <div className="chips">
              {config.audiences.map((a) => (
                <button key={a.level} type="button"
                        className={`chip${level === a.level ? " active" : ""}`}
                        onClick={() => setLevel(a.level)}>
                  {a.level}
                </button>
              ))}
            </div>
            <p className="hint">
              {config.audiences.find((a) => a.level === level)?.description}
            </p>
          </fieldset>
        )}

        <label className="checkbox">
          <input type="checkbox" checked={useCache} onChange={(e) => setUseCache(e.target.checked)} />
          <span>Reuse cached OCR for the same PDF and vision model</span>
        </label>

        <div className="row actions">
          <button type="button" className="primary" disabled={!ready || running} onClick={generate}>
            {running ? "Processing…" : "Run pipeline"}
          </button>
          <button type="button" className="ghost" disabled={running} onClick={() => refreshFiles()}>
            Refresh files
          </button>
        </div>
      </section>

      <StreamPanel stream={stream}
                   emptyHint="Pick a PDF and run the pipeline — pages stream in as they're transcribed." />
    </div>
  );
}
