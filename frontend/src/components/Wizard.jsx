import { MUTED, PRIMARY, QUIET, ROW } from "../styles.js";

/**
 * One decision at a time. A step that has been answered collapses to its answer, the
 * current step is the only live one, and the steps ahead stay on screen — dimmed and
 * inert — so the shape of the whole form is readable before any of it is filled in.
 *
 * `current` is owned by the caller: a form whose submit fails has to be able to send the
 * reader back to the one step that can fix it, and a step can hand Continue somewhere
 * other than the next step with `onContinue`.
 */
export default function Wizard({ steps, current, onCurrent }) {
  return (
    <ol className="flex flex-col">
      {steps.map((step, index) => {
        const state = index < current ? "done" : index === current ? "current" : "ahead";
        return (
          <li
            key={step.id}
            className={`grid grid-cols-[26px_minmax(0,1fr)] gap-x-3 py-3.5 border-t border-line
                        first:border-t-0 first:pt-0 ${state === "ahead" ? "opacity-40" : ""}`}
          >
            <span
              className={`font-mono text-xs pt-0.5 ${
                state === "current" ? "text-accent" : "text-muted"
              }`}
            >
              {String(index + 1).padStart(2, "0")}
            </span>

            {state === "done" ? (
              <div className="flex items-baseline gap-2.5 flex-wrap">
                <span className="text-sm text-muted">{step.title}</span>
                <span className="text-sm font-medium [overflow-wrap:anywhere]">{step.summary}</span>
                <button
                  type="button"
                  className={`${QUIET} ml-auto`}
                  onClick={() => onCurrent(index)}
                >
                  Change
                </button>
              </div>
            ) : (
              // Ahead steps keep their real controls rather than a mock-up of them: it is
              // the same markup either way, and `inert` is what stops it being reachable
              // by a click, a tab, or a screen reader while it is only a preview.
              <div className="grid gap-3" inert={state === "ahead"}>
                <div>
                  <h3 className="text-sm font-semibold">{step.title}</h3>
                  {step.hint && <p className={MUTED}>{step.hint}</p>}
                </div>

                {step.body}

                {/* `action` is checked for presence, not truth: a step that renders its
                    own controls passes null to say "no Continue button here". */}
                {state === "current" &&
                  (step.action !== undefined ? (
                    step.action
                  ) : (
                    <div className={ROW}>
                      <button
                        type="button"
                        className={PRIMARY}
                        disabled={!step.complete}
                        onClick={() => (step.onContinue ?? (() => onCurrent(index + 1)))()}
                      >
                        Continue
                      </button>
                    </div>
                  ))}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
