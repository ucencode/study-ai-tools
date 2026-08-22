import { CURRICULUM, SLIDES } from "../api.js";

// The status vocabulary, used identically everywhere.
export const STATUS_GLYPH = { queued: "○", processing: "●", completed: "✓", failed: "×" };
export const STATUS_LABEL = {
  queued: "Waiting",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

const STAGE_LABEL = {
  convert: "Convert",
  ocr: "OCR",
  refine: "Refine",
  metadata: "Metadata",
  plan: "Plan",
  outline: "Outline",
  material: "Material",
  references: "References",
  chapters: "Chapters",
};

// Stages whose counter counts real items. `material`/`references` share a two-step
// counter that means nothing to a reader, so they are shown without one.
const COUNTED = { ocr: "pages", chapters: "chapters" };

export const isTerminal = (status) => status === "completed" || status === "failed";

export const stageLabel = (name) => STAGE_LABEL[name] || name;

// Branches, not one sequence: derived from the job's own params every time.
export function stagesFor(job) {
  if (job.service === SLIDES) {
    const names = [];
    if (job.params.source_format === "pptx") names.push("convert");
    names.push("ocr");
    if (job.params.action !== "skip") names.push("refine");
    return names;
  }
  const names = ["metadata", "plan", "outline"];
  return job.params.mode === "full"
    ? [...names, "chapters"]
    : [...names, "material", "references"];
}

// `progress` is cleared the moment a job ends, so a finished job is described by what
// it durably left behind rather than by a counter that no longer exists.
function evidence(job) {
  const done = [];
  const counts = {};

  if (job.service !== CURRICULUM) {
    if (job.result?.pages) counts.ocr = { current: job.result.pages, total: job.result.pages };
    return { done, counts };
  }

  if (job.result) done.push("metadata");
  if (job.outline?.length) done.push("plan", "outline");
  if (job.params.mode === "full" && job.outline?.length) {
    counts.chapters = { current: job.chapters?.length || 0, total: job.outline.length };
  }
  return { done, counts };
}

export function stageStates(job) {
  const names = stagesFor(job);
  const done = new Set();
  const counts = {};
  let active = null;

  if (job.status === "completed") {
    names.forEach((name) => done.add(name));
    Object.assign(counts, evidence(job).counts);
  } else if (job.status === "processing" && job.progress) {
    const { stage, current, total } = job.progress;
    const index = names.indexOf(stage);
    if (index >= 0) {
      names.slice(0, index).forEach((name) => done.add(name));
      counts[stage] = { current, total };
      if (total > 0 && current >= total) done.add(stage);
      else active = stage;
    }
  } else if (job.status === "failed") {
    const known = evidence(job);
    known.done.forEach((name) => done.add(name));
    Object.assign(counts, known.counts);
  }

  return names.map((name) => ({
    name,
    label: stageLabel(name),
    state: done.has(name) ? "done" : name === active ? "active" : "pending",
    unit: COUNTED[name],
    counts: COUNTED[name] ? counts[name] : undefined,
  }));
}

// The one-line summary used in the jobs rail and the detail header.
export function statusLine(job) {
  if (job.status === "queued") return "Waiting for the worker";
  if (job.status !== "processing") return STATUS_LABEL[job.status];
  if (!job.progress) return "Starting";

  const { stage, current, total } = job.progress;
  const unit = COUNTED[stage];
  if (!unit || total <= 1) return stageLabel(stage);
  return `${stageLabel(stage)} · ${current} / ${total} ${unit}`;
}

export default function Stages({ job }) {
  // Nothing has run yet, so there is no progress to draw.
  if (job.status === "queued") {
    return <p className="waiting">○ Waiting for the worker</p>;
  }

  return (
    <ul className="stages">
      {stageStates(job).map(({ name, label, state, counts }) => (
        <li key={name} className={`stage stage-${state}`}>
          <span className="stage-glyph">
            {state === "done" ? "✓" : state === "active" ? "●" : "○"}
          </span>
          <span className="stage-label">{label}</span>
          {counts && counts.total > 1 && (
            <span className="stage-count mono">
              {counts.current} / {counts.total}
            </span>
          )}
          {state === "active" && counts && counts.total > 1 && (
            <span className="stage-bar">
              <span style={{ width: `${(counts.current / counts.total) * 100}%` }} />
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
