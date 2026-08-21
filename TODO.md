# TODO

Known gaps after the job-based rewrite (#3). Roughly in priority order.

## Tests — nothing is committed

Every claim in #3 was verified with throwaway scripts that live outside the repo, so
**the pipelines currently have zero automated coverage**. This is the highest-value item:
the logic is no longer trivial, and the next refactor has nothing to catch it.

Needs `pytest` + `pytest-asyncio`, and a fake `llm` module fixture (stub `complete`,
`complete_json`, `stream_chat`, `unload`, `list_models`) so nothing touches Ollama.

Scenarios worth locking down, all of which were checked by hand once:

| Scenario | Assertion |
|---|---|
| Slides pipeline | `queued → processing → completed`, progress advances |
| Page OCR failure | `[missing page N]` written, run continues |
| OCR cache | same bytes → reused; same filename + different bytes → **not** reused |
| PPTX | `converted.pdf` appears; no LibreOffice → `400` at submit |
| Curriculum full mode | one chapter file per topic, no duplicates |
| Outline pruning | forward references and invented topics dropped |
| `depends_on: []` | no `### Building On`; with a dep → present |
| Ledger marker | stripped from chapter files, stored in `job.json` |
| Crash + retry | resumes at the next chapter, same job id |
| `include_plan=false` | `plan.md` on disk, absent from `output.md` |
| FIFO | second job stays `queued` until the first finishes |
| Orphan recovery | in-flight jobs from a dead process → `failed` at startup |
| Guards | delete/retry live job → `409`; oversized upload → `413` |

## Frontend

React + Vite against the polling API. The `legacy-web` tag holds the previous job-aware UI
(`frontend/src/components/Jobs.jsx`, `useLastJob.js`) as a reference — but it was written
for an SSE endpoint that no longer exists, so the data flow needs rewriting for polling.
CORS is already configured for a Vite dev server on localhost.

## Correctness and robustness

| Item | Notes |
|---|---|
| Job locking | The API and CLI both refuse to touch a `queued`/`processing` job, but that is a status check, not a lock — it cannot close the window between the check and `run()`. A lockfile in the job directory would, if this ever stops being single-user. |
| Slide OCR checkpointing | Retrying a slide job restarts OCR from page one. `raw.txt` is already written incrementally, so resuming from its page count is a small change. |
| Stray chapter files | A chapter that crashes mid-write leaves an empty `chapters/NN.md` that `job.chapters` does not list. Harmless — it gets overwritten on retry — but never cleaned up. |
| No cancel | A 40-minute job started by mistake runs to completion or the server restarts. Deliberate, but worth revisiting once the UI exists. |
| Single worker not enforced | The queue lives in the process. `uvicorn --workers 2` would silently create two independent queues, both feeding one GPU. Documented only. |

## Smaller

| Item | Notes |
|---|---|
| `config/models.toml` | Goes stale as Ollama ships models. Needs periodic updating; unlisted models work but get no role hints. |
| Quiz flow | Answers must be supplied at submit. No way to create a job, then answer later. |
| Cloud detection | `llm.is_cloud()` matches `-cloud` / `:cloud` by name. Fine today, but it is a naming convention, not an API guarantee. |
| Prompt tuning | The token work in #3 is estimated from prompt token counts, never measured against a live model. Worth confirming the prefix-cache assumption with real timings. |
