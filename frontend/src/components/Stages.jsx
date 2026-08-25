import { CURRICULUM, SLIDES } from "../api.js";

// The status vocabulary, used identically everywhere.
export const STATUS_GLYPH = { queued: "○", processing: "●", completed: "✓", failed: "×" };
export const STATUS_LABEL = {
  queued: "Waiting",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};
export const STATUS_COLOUR = {
  queued: "text-waiting",
  processing: "text-processing",
  completed: "text-ok",
  failed: "text-fail",
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

// Every view names a job the same way: whatever the user actually supplied.
export const jobLabel = (job) =>
  job.params.filename || job.params.source_name || job.id;

// A browser tab truncates hard, and this app is built to be left running in the
// background, so the glyph and the fraction come before the name — those are what
// survive at six characters. `statusLine` below is the same facts for a UI with room.
export function tabTitle(job) {
  const { current, total } = job.progress || {};
  const count = total > 1 ? `${current}/${total} · ` : "";
  return `${STATUS_GLYPH[job.status]} ${count}${jobLabel(job)}`;
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
    return <p className="text-sm text-waiting">○ Waiting for the worker</p>;
  }

  return (
    <ul className="grid gap-2 max-w-[340px]">
      {stageStates(job).map(({ name, label, state, counts }) => (
        // `data-state` is what the glyph and label colour off, so the row states
        // stay in one place instead of being recomputed per child.
        <li
          key={name}
          data-state={state}
          className="group grid grid-cols-[14px_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-1
                     text-sm data-[state=pending]:text-muted"
        >
          <span className="text-waiting group-data-[state=done]:text-ok group-data-[state=active]:text-processing">
            {state === "done" ? "✓" : state === "active" ? "●" : "○"}
          </span>
          <span className="group-data-[state=active]:font-medium">{label}</span>
          {counts && counts.total > 1 && (
            <span className="text-xs text-muted font-mono">
              {counts.current} / {counts.total}
            </span>
          )}
          {state === "active" && counts && counts.total > 1 && (
            <span className="col-start-2 -col-end-1 h-[3px] rounded-sm bg-line overflow-hidden">
              <span
                className="block h-full bg-processing"
                style={{ width: `${(counts.current / counts.total) * 100}%` }}
              />
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
