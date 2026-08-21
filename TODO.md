# Next: React + Vite frontend

> **Brief for the next coding agent.** Read [CLAUDE.md](CLAUDE.md) first — the backend's
> invariants and design stance apply here too. This document is the spec; implement it
> rather than re-planning it. Where it is silent, pick the boring option.

## Objective

Build the web UI for both pipelines. The backend (PR #3) is complete and job-based: submit
returns an id, one worker runs jobs FIFO, clients **poll**. There is no SSE, no websocket,
no push. The UI's job is to make submitting easy and waiting legible.

Ship into `frontend/`, served by Vite in dev against `http://localhost:8000`. CORS is
already configured for `localhost:*`.

**Reference, with a caveat:** the `legacy-web` tag has an earlier UI for this project
(`frontend/src/components/{Jobs,Slides,StudyPlan,Outputs,StreamPanel}.jsx`). Its layout and
styling are worth stealing. Its data flow is **not** — it was built on an SSE endpoint that
no longer exists (`useStream.js`, `StreamPanel.jsx`). Do not port those.

## Constraints

| Constraint | Detail |
|---|---|
| Plain React | No Redux, no react-query, no component library. `useState`/`useEffect` and `fetch`. |
| No build-time API client | Hand-write `api.js`. Do not generate from OpenAPI. |
| Poll, don't push | See the polling section. Never add SSE "because it's nicer". |
| One job at a time | The backend runs a single FIFO worker. The UI must show a queued job as *waiting*, not stuck. |
| Fail visibly | An error from the API is rendered, never swallowed into a spinner that spins forever. |

## API contract

Base `http://localhost:8000/api`. `{service}` is `slide-summarizer` or `curriculum-generator`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | `{status, ollama: "up"\|"down", libreoffice: bool}` |
| `GET` | `/config` | `{languages[], audiences[], actions[], modes[], pptx_enabled}` |
| `GET` | `/models` | `{models[], vision[], refine[], llm[]}` |
| `GET` | `/jobs?service_name=` | Both services merged, newest first |
| `POST` | `/slide-summarizer/jobs` | **multipart**, `202` |
| `POST` | `/curriculum-generator/quiz` | `{curriculum, model}` → `{questions[], topics[], metadata}` |
| `POST` | `/curriculum-generator/jobs` | JSON, `202` |
| `GET` | `/{service}/jobs/{id}` | Full job record |
| `GET` | `/{service}/jobs/{id}/output` | `{id, content}` — partial while running |
| `POST` | `/{service}/jobs/{id}/retry` | `202`; `409` if queued/processing |
| `DELETE` | `/{service}/jobs/{id}` | `204`; `409` if queued/processing |

Job record:

```js
{ id, service, status: "queued"|"processing"|"completed"|"failed",
  created_at, updated_at, started_at, finished_at,
  progress: { stage, current, total } | null,   // null unless processing
  error: string | null, input_path, output_path: string | null,
  params: {...}, result: {...} | null,
  outline: [{topic, scope, depends_on[]}],      // curriculum only
  chapters: [{topic, file, established[]}] }    // curriculum only
```

`progress.stage` is `convert`|`ocr`|`refine` for slides, `metadata`|`plan`|`outline`|`material`|`references`|`chapters` for curriculum.

Slide submit is multipart: `file` plus form fields `ocr_model`, `action`, `refine_model`,
`lang`, `level`, `dpi`. Everything else is JSON.

Error responses are `{detail: "..."}`. Meaningful codes: `400` wrong file type, `409` job is
live, `413` over 200 MB, `422` bad params, `503` Ollama unreachable.

## Files

```
frontend/
  index.html
  package.json           react, react-dom, vite, @vitejs/plugin-react — nothing else
  vite.config.js         proxy /api -> http://localhost:8000
  src/
    main.jsx
    App.jsx              tab switch + <JobList/>; owns activeJobId
    api.js               one function per endpoint; throws ApiError{status, detail}
    usePolling.js        the only polling primitive
    components/
      SlidesForm.jsx     file picker + options -> POST multipart
      CurriculumForm.jsx textarea + options + quiz step -> POST json
      Quiz.jsx           renders questions, collects Y/N, returns answers[]
      JobList.jsx        GET /jobs every 5s; select a job
      JobDetail.jsx      status, progress, error, retry/delete
      Output.jsx         output text; re-fetch while processing
      Health.jsx         banner when ollama is down or libreoffice missing
    styles.css
```

## Polling

One hook, used everywhere:

```js
// usePolling(fetcher, intervalMs, active) -> {data, error, loading}
```

Rules that matter:

- **Stop when the job is terminal.** `completed`/`failed` means no more requests. A polling
  loop that never stops is the main way this UI can go wrong.
- Intervals: job list `5000`, active job detail `1500`, output while processing `3000`.
  Don't go below 1000 — the worker writes `job.json` on every progress tick and there is
  nothing to gain.
- Skip a tick if the previous request is still in flight.
- Clear the interval on unmount and when `active` goes false.
- A failed poll should surface after ~3 consecutive failures, not the first — the dev server
  restarting shouldn't flash an error.

## Behaviour

**Health.** Fetch once on mount. If `ollama: "down"`, show a persistent banner and disable
both submit buttons — every job would fail anyway. If `libreoffice: false`, allow PDF and
disable PPTX with the reason shown, don't hide it.

**Slides form.** Drag-or-pick a `.pdf`/`.pptx`. Model select from `models.vision`; if that
array is empty, fall back to `models.models` with a visible warning that nothing in
`config/models.toml` is marked `vision` — mirror the CLI's behaviour, don't silently offer
everything. Refine model, language, and audience level only appear when `action !== "skip"`.
DPI defaults to 200.

**Curriculum form.** Textarea for the curriculum (a file drop that reads to text is fine).
Model from `models.llm`. Then:

1. Unless the user skips it, `POST /quiz` and render `<Quiz/>`. This blocks on a human by
   design — the answers calibrate depth.
2. Submit with `questions` and `answers` passed straight through.
3. `mode` is `short`|`full`. `include_plan` is a checkbox, default on, labelled so it's clear
   the plan is still *generated* either way — it only controls whether it appears in the
   document. Copy: *"Include the study plan in the document"*.

**Job list.** Both services, newest first, with service, status, created time, and a label
from `params` (`filename` or `source_name`). A `queued` job must read as *waiting for the
worker*, not as broken — say so in the UI.

**Job detail.** For `processing`, show `stage` and `current/total` as a bar. For `failed`,
show `error` and a Retry button. Retry and Delete must handle `409` by refreshing rather than
showing a raw error — it means the job went live between render and click.

**Output.** Fetch `/output`; render as preformatted text (markdown rendering is optional and
explicitly out of scope for v1). Keep polling while `processing` so the document visibly
grows. Offer a copy-to-clipboard.

**Curriculum extras.** When `outline` is present, render it as a chapter list showing each
topic's `depends_on` — that is the structure the whole full-mode design turns on, and seeing
it is how you tell whether the model got it right.

## Acceptance

- [ ] `cd frontend && npm install && npm run dev` works against `uv run fastapi dev`
- [ ] Submit a PDF, watch status go `queued → processing → completed` without a refresh
- [ ] The OCR progress bar advances page by page
- [ ] Submit a curriculum in `full` mode; chapter count climbs as chapters finish
- [ ] Output pane grows while the job runs
- [ ] Polling **stops** once a job is terminal — confirm in devtools Network
- [ ] Kill the backend mid-job: UI shows an error, recovers when it returns
- [ ] Retry a failed job — same id, resumes rather than restarting
- [ ] Delete a running job → `409` handled without a raw error dialog
- [ ] Ollama stopped → banner shown, submits disabled
- [ ] Two jobs submitted back to back → second shows as queued, then runs

## Also worth doing

Not part of this brief, but the backend's real gap: **there are no committed tests**. Every
claim in PR #3 was verified with throwaway scripts that were never checked in. CLAUDE.md
documents the fake-`llm` fixture pattern and the thirteen scenarios worth locking down. If
you have appetite before the UI, that is where it should go.

Smaller known gaps: retrying a slide job restarts OCR from page one; a crashed chapter leaves
an orphaned `chapters/NN.md` that is ignored but never cleaned; there is no cancel; the
single-worker requirement is documented but not enforced; `config/models.toml` goes stale as
Ollama ships models.
