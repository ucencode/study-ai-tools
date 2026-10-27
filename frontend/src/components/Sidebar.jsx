import { CURRICULUM, SETTINGS, SLIDES } from "../api.js";

const PIPELINES = [
  { id: SLIDES, label: "Slides" },
  { id: CURRICULUM, label: "Curriculum" },
];

// Narrow, the rail stops being a column and becomes a row of tabs above the workspace,
// so the selected marker moves from the left edge to the bottom edge.
// No background here: `bg-transparent` in the shared half would outrank the selected
// half's `bg-accent-weak`, since both land in the same class list.
const PIPELINE_BASE =
  "block w-full text-left px-3.5 py-1.5 border-l-2 text-sm " +
  "max-rail:w-auto max-rail:border-l-0 max-rail:border-b-2 max-rail:px-2.5";

export default function Sidebar({ active, onSelect }) {
  const entry = ({ id, label }) => (
    <button
      key={id}
      type="button"
      className={`${PIPELINE_BASE} ${
        active === id
          ? "border-l-accent bg-accent-weak text-fg font-medium max-rail:border-l-transparent max-rail:border-b-accent"
          : "border-transparent bg-transparent text-muted hover:text-fg"
      }`}
      aria-current={active === id ? "page" : undefined}
      onClick={() => onSelect(id)}
    >
      {label}
    </button>
  );

  return (
    <nav
      className="border-r border-line py-3.5 max-rail:flex max-rail:items-center max-rail:gap-1
                 max-rail:border-r-0 max-rail:border-b max-rail:px-2.5 max-rail:py-1.5"
      aria-label="Pipelines"
    >
      <h2 className="px-3.5 mb-2 text-xs font-semibold uppercase tracking-wider text-muted max-rail:hidden">
        Pipelines
      </h2>
      {PIPELINES.map(entry)}
      {/* Apart from the pipelines: it configures them rather than being one. Narrow, it
          is pushed to the far end of the tab row instead. */}
      <div className="mt-4 pt-3.5 border-t border-line max-rail:mt-0 max-rail:pt-0 max-rail:border-t-0 max-rail:ml-auto">
        {entry({ id: SETTINGS, label: "Settings" })}
      </div>
    </nav>
  );
}
