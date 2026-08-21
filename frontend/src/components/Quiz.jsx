export default function Quiz({ questions, answers, onAnswer, onBack, onStart, busy }) {
  const known = new Map(answers.map((answer) => [answer.id, answer.known]));

  return (
    <section className="quiz">
      <h3 className="section-heading">Calibration</h3>
      <p className="secondary">
        Answer a few questions so the material can skip what you already know.
      </p>

      <ol className="questions">
        {questions.map((question, index) => (
          <li key={question.id}>
            <span className="question-number mono">{String(index + 1).padStart(2, "0")}</span>
            <div className="question-body">
              <p className="question-text">{question.question}</p>
              {question.topic && <p className="secondary">{question.topic}</p>}
            </div>
            <div className="question-answer">
              {[true, false].map((value) => (
                <label key={String(value)}>
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

      <div className="row end">
        <button type="button" className="secondary-button" onClick={onBack} disabled={busy}>
          Back
        </button>
        <button type="button" className="primary" onClick={onStart} disabled={busy}>
          {busy ? "Submitting…" : "Start generation"}
        </button>
      </div>
    </section>
  );
}
