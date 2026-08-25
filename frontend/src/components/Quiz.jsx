import { MUTED, PRIMARY, SECONDARY_BUTTON } from "../styles.js";

export default function Quiz({ questions, answers, onAnswer, onBack, onStart, busy }) {
  const known = new Map(answers.map((answer) => [answer.id, answer.known]));
  const unanswered = questions.length - known.size;

  return (
    <section className="border-t border-line pt-3.5 grid gap-2.5">
      <h3 className="text-sm font-semibold">Calibration</h3>
      <p className={MUTED}>
        Answer a few questions so the material can skip what you already know.
      </p>

      <ol>
        {questions.map((question, index) => (
          <li
            key={question.id}
            className="grid grid-cols-[26px_minmax(0,1fr)_auto] gap-3 items-center py-2.5
                       border-t border-line max-rail:grid-cols-[26px_minmax(0,1fr)]"
          >
            <span className="text-xs text-muted font-mono">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <p className="text-sm">{question.question}</p>
              {question.topic && <p className={MUTED}>{question.topic}</p>}
            </div>
            <div className="flex gap-3.5 text-sm max-rail:col-start-2 max-rail:justify-start">
              {[true, false].map((value) => (
                <label key={String(value)} className="inline-flex items-center gap-1.5">
                  <input
                    type="radio"
                    name={`question-${question.id}`}
                    checked={known.get(question.id) === value}
                    onChange={() => onAnswer(question.id, value)}
                  />
                  {value ? "Yes" : "No"}
                </label>
              ))}
            </div>
          </li>
        ))}
      </ol>

      <div className="flex items-center gap-2.5 flex-wrap justify-end">
        {unanswered > 0 && (
          <p className={MUTED}>
            {unanswered} unanswered — answer them, or go back and skip calibration.
          </p>
        )}
        <button type="button" className={SECONDARY_BUTTON} onClick={onBack} disabled={busy}>
          Back
        </button>
        <button
          type="button"
          className={PRIMARY}
          onClick={onStart}
          disabled={busy || unanswered > 0}
        >
          {busy ? "Submitting…" : "Start generation"}
        </button>
      </div>
    </section>
  );
}
