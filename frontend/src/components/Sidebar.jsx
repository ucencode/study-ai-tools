import { CURRICULUM, SLIDES } from "../api.js";

const PIPELINES = [
  { id: SLIDES, label: "Slides" },
  { id: CURRICULUM, label: "Curriculum" },
];

export default function Sidebar({ active, onSelect }) {
  return (
    <nav className="sidebar" aria-label="Pipelines">
      <h2 className="rail-heading">Pipelines</h2>
      {PIPELINES.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          className={`pipeline${active === id ? " selected" : ""}`}
          aria-current={active === id ? "page" : undefined}
          onClick={() => onSelect(id)}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
