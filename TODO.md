# Delivered: React + Vite frontend

> **Built — this stays the spec.** It was written as a brief for the next coding agent and
> is kept as the record of what the UI is supposed to do, so read it before changing the
> frontend. [CLAUDE.md](CLAUDE.md) carries the backend's invariants and design stance, which
> apply here too. Where this document is silent, pick the boring option.

## Objective

Build the web UI for both pipelines. The backend (PR #3) is complete and job-based: submit
returns an id, one worker runs jobs FIFO, clients **poll**. There is no SSE, no websocket,
no push. The UI's job is to make submitting easy and waiting legible.

Ship into `frontend/`, served by Vite in dev against `http://localhost:8000`. CORS is
already configured for `localhost:*`.

**The design thesis:** *let the backend architecture leak into the UI in useful ways.* That
there is one worker, that jobs queue, that they move through named stages, that output grows
on disk, that chapters declare dependencies, that retry resumes — this is the subject matter.
Hiding it behind a generic "Generating…" spinner makes the app worse, not just plainer.

**Reference, with a caveat:** the `legacy-web` tag has an earlier UI for this project
(`frontend/src/components/{Jobs,Slides,StudyPlan,Outputs,StreamPanel}.jsx`). Its layout and
styling are worth stealing. Its data flow is **not** — it was built on an SSE endpoint that
no longer exists (`useStream.js`, `StreamPanel.jsx`). Do not port those.

## Constraints

| Constraint | Detail |
|---|---|
| Plain React | No Redux, no react-query, no component library. `useState`/`useEffect` and `fetch`. |
| No new dependencies | `react`, `react-dom`, `vite`, `@vitejs/plugin-react`. Nothing else — no icon packs, no web fonts. |
| No build-time API client | Hand-write `api.js`. Do not generate from OpenAPI. |
| Poll, don't push | See [Polling](#polling). Never add SSE "because it's nicer". |
| One job at a time | Single FIFO worker. A queued job must read as *waiting*, not stuck. |
| Fail visibly, inline | Errors render in place. No `alert()`, no toast for anything persistent. |

## Visual language

A local processing workstation, closer to Linear or GitHub Actions than to a chat product.
Neutral surfaces, thin borders, compact type, one accent colour, no decorative gradients.

```
Background       #f7f7f5      Accent     muted blue/indigo — exactly one
Panel            #ffffff      Waiting    neutral gray
Border           #dededb      Processing blue
Primary text     #20201e      Completed  green
Secondary text   #6f6f69      Failed     red
```

Define these as CSS custom properties on `:root` from the start, and add a
`prefers-color-scheme: dark` block that redefines only the tokens. Retrofitting a dark theme
later is painful; doing it up front is ~15 lines. You will be looking at this during
40-minute full-textbook runs.

```css
font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
```

Monospace for **job ids, stage names, counts and output only**. Do not make the whole
application monospace — that is developer-tool cosplay, and it hurts the forms.

| Element | Size / weight |
|---|---|
| Page title | 20–22px / 600 |
| Section heading | 14–16px / 600 |
| Body | 14px |
| Secondary | 12–13px |
| Labels | 12px / 500 |
| Job ids | 11–12px mono |

`border-radius: 6px`, buttons ~34px tall. Three button levels only — primary
(`Start processing`), secondary (`Retry`), quiet text (`Copy`, `Delete`, `Change file`). Not
every action gets a filled rectangle. No fully-rounded pills.

Status vocabulary, used identically everywhere:

```
○ Waiting      ● Processing      ✓ Completed      × Failed
```

One line per job, not three badges. `● OCR · 14 / 31 pages` beats
`[PROCESSING] [OCR] [SLIDES]`.

**Naming.** Buttons say what happens: `Start processing`, not `Generate`, `Transform`, or
anything with a sparkle. Headings are `Job output` and `Configuration`, never "Here's your
result". No illustrations in empty states.

## Layout

Desktop-first. Three persistent concepts — which pipeline, what you're doing, what the
worker is doing — so three columns.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Study Tools                              Ollama ●   LibreOffice ✓    │
├───────────────┬──────────────────────────────┬───────────────────────┤
│  PIPELINES    │  WORKSPACE                   │  JOBS                 │
│               │                              │  1 running · 2 waiting│
│ │Slides       │  [form, or job detail]       │                       │
│  Curriculum   │                              │  PROCESSING           │
│               │                              │  ● Slide summary      │
│               │                              │    report.pdf         │
│               │                              │    OCR · 14 / 31      │
│               │                              │                       │
│               │                              │  WAITING              │
│               │                              │  ○ Curriculum         │
│               │                              │    Waiting for worker │
└───────────────┴──────────────────────────────┴───────────────────────┘
   160–190px          flexible, min 600px            280–330px
```

Selected pipeline marked with a 2px left border, not a pill. Below ~900px the jobs rail
becomes a collapsible bottom section.

**The count is `1 running · 2 waiting`, never "3 active".** With one worker, at most one job
can be running; "active" implies parallelism the backend does not have.

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

```js
{ id,                                          // "20260822143012-a3f9" — timestamp + 4 hex
  service, status: "queued"|"processing"|"completed"|"failed",
  created_at, updated_at, started_at, finished_at,
  progress: { stage, current, total } | null,  // null unless processing
  error: string | null,                        // "LLMError: could not reach Ollama (...)"
  input_path, output_path: string | null,
  params: {...}, result: {...} | null,
  outline: [{topic, scope, depends_on[]}],     // curriculum only
  chapters: [{topic, file, established[]}] }   // curriculum only
```

Slide submit is multipart: `file` plus form fields `ocr_model`, `action`, `refine_model`,
`lang`, `level`, `dpi`. Everything else is JSON. Errors are `{detail: "..."}` — `400` wrong
file type, `409` job is live, `413` over 200 MB, `422` bad params, `503` Ollama unreachable.

### Stages are mode-dependent — get this right

Render a stage checklist, not one generic bar. But the stage sets are **branches, not a
single sequence**:

| Pipeline | Stages |
|---|---|
| Slides | `convert` *(pptx only)* → `ocr` → `refine` *(omitted when `action="skip"`)* |
| Curriculum, **short** | `metadata` → `plan` → `outline` → `material` → `references` |
| Curriculum, **full** | `metadata` → `plan` → `outline` → `chapters` |

`material`/`references` and `chapters` are **mutually exclusive** — one is short mode, the
other full mode. A job can never show both. Derive the checklist from `params.mode` and
`params.action`, never from a hardcoded list of every stage name.

```
✓ Metadata          ✓ Convert
✓ Plan              ● OCR       14 / 31
✓ Outline           ○ Refine
● Chapters   3 / 8
```

Queued shows `○ Waiting for worker` with **no progress bar** — there is no progress yet.

**Never show an estimated time remaining.** You have no basis for one: OCR pages vary wildly
in complexity and chapters vary in length. A fabricated ETA is worse than none.

## Files

```
frontend/
  index.html
  package.json           react, react-dom, vite, @vitejs/plugin-react — nothing else
  vite.config.js         proxy /api -> http://localhost:8000
  src/
    main.jsx
    App.jsx              three-column shell; owns activeTab + activeJobId
    api.js               one function per endpoint; throws ApiError{status, detail}
    usePolling.js        the only polling primitive
    components/
      Header.jsx         title + health indicators
      Sidebar.jsx        pipeline switch
      SlidesForm.jsx     dropzone + config -> POST multipart
      CurriculumForm.jsx source + config + quiz step -> POST json
      Quiz.jsx           calibration questions -> answers[]
      JobList.jsx        the rail: grouped by state, polls /jobs
      JobDetail.jsx      status, stages, timings, retry/delete
      Stages.jsx         the mode-dependent checklist
      Outline.jsx        curriculum chapter list + depends_on
      Output.jsx         the growing document
    styles.css
```

## Polling

One hook, used everywhere:

```js
// usePolling(fetcher, intervalMs, active) -> {data, error, stale}
```

- **Stop when the job is terminal.** `completed`/`failed` means no more requests. A loop that
  never stops is the main way this UI can go wrong.
- Intervals: job list `5000`, active job detail `1500`, output while processing `3000`. Never
  below `1000` — the worker rewrites `job.json` on every progress tick and there is nothing
  to gain.
- Skip a tick if the previous request is still in flight. Clear on unmount and when `active`
  goes false.

**Connection loss.** Do not replace the view with an error state — keep the last known data
visible and mark it stale. After ~3 consecutive failures:

```
● Processing
OCR · 14 / 31
Last updated 18s ago · connection unavailable
```

Keep retrying. On recovery show `Connected` for ~3s, then let it disappear. A dev-server
restart should not wipe the screen.

## Screens

### Header and health

Fetch `/health` on mount and every 15s. Compact indicators in the header: `Ollama ●`,
`LibreOffice ✓`.

If `ollama: "down"`, an **amber** bar (this is a normal state — you forgot to start it, not a
catastrophe) and both submit buttons disabled:

```
Ollama is unavailable. New jobs cannot be submitted.          Retry
```

Reserve red for actual job failure. If `libreoffice: false`, an inline note in the slides
form — `LibreOffice not installed — PPTX input unavailable. PDF still works.` — and `.pptx`
shown **disabled** in the picker rather than silently absent.

### Slides form

Dropzone for `.pdf`/`.pptx`, `PDF · PPTX · max 200 MB`. Once a file is chosen, **replace the
dropzone** with a compact row — `architecture-review.pdf · 18.4 MB · Change file`. Leaving a
giant dropzone sitting there is the tell that nobody used the thing they built.

Aligned label/control rows, not a card per field:

```
OCR model        qwen3-vl:8b        ▾
Action           Summary            ▾
Refine model     gemma3:12b         ▾
Language         English            ▾
Audience         Intermediate       ▾      beginner | intermediate | advanced
DPI              200
```

Refine model, language and audience appear only when `action !== "skip"` — conditional
fields, no accordion, no animation. Audience only applies to `summary` and `deep`.

**Model fallback.** If `models.vision` is empty, fall back to `models.models` and show a
small, **persistent, inline** warning under the field:

```
⚠ No installed model is marked `vision` in config/models.toml.
  Showing all models — pick one that actually supports images.
```

Not a toast. A toast vanishes and then the user wonders why `mistral` is in an OCR dropdown.

### Curriculum form

Three steps, a tiny horizontal indicator — `1 Source · 2 Calibration · 3 Generate`. Not a
wizard with big circles.

Textarea for the curriculum (dropping a text file that reads into it is fine). Model from
`models.llm`. Mode defaults to **Short** — Full is one model call per chapter and can run
30–60 minutes, so it should be a deliberate choice.

```
☑ Include the study plan in the document
   The study plan is generated either way. This controls only whether it
   appears in the final document.
```

That second line goes **in the UI**, not in a tooltip. It is the whole point of the flag.

### Quiz

Deliberately not chat-shaped. It is calibration, not a conversation.

```
Calibration
Answer a few questions so the material can skip what you already know.

01  Are you comfortable with relational joins?      (●) Yes  ( ) No
02  Have you used transactions before?              ( ) Yes  (●) No

                                        [ Back ]  [ Start generation ]
```

Disable the source textarea while the quiz is showing. Pass `questions` and `answers`
straight through to the job payload unchanged.

### Jobs rail

Grouped `PROCESSING` / `WAITING` / `RECENT`, each row showing service, the label from
`params.filename` or `params.source_name`, status line, and relative time. Selecting a row
swaps the workspace to `JobDetail`.

Say **"Waiting for the worker"**, not just "Queued" — a person who does not know the system
cannot tell whether queued is healthy.

Empty: `No jobs yet — submitted jobs appear here.` No illustration.

### Job detail

```
architecture-review.pdf
Slide summarizer · Processing
20260822143012-a3f9                    Created 04:16:41  Started 04:16:43
```

Stage checklist (see above), then plain timings. Duration on completion is
`finished_at - started_at`.

**Failed jobs.** `error` is a Python exception string — `f"{type(e).__name__}: {e}"` — not
prose written for a reader. Render it verbatim in a `<pre>` with a red border. Do not try to
prettify it; if friendlier errors are wanted, that is a backend change.

```
× Failed
┌──────────────────────────────────────────────────────────┐
│ LLMError: could not reach Ollama — is it running? (...)   │
└──────────────────────────────────────────────────────────┘
[ Retry job ]   Delete
```

**Retry semantics differ by pipeline, and the microcopy must not lie:**

| Pipeline | What retry does | Copy |
|---|---|---|
| Curriculum | Resumes from the last finished chapter | `Resumes from chapter N — finished chapters are kept.` |
| Slides | Re-runs the whole pipeline; **OCR restarts from page one** | `Re-runs this job from the beginning.` |

No "Danger zone" section. One destructive action on a local single-user tool does not need
GitHub's ceremony — a quiet `Delete` is enough.

### 409 handling

`409` means the job went live between render and click. It is a race, not an error. Refresh
the job and show an inline note near the buttons — never a dialog:

- Delete → `Job started processing before it could be deleted.`
- Retry → `This job has already resumed.`

### Output

Below the progress section on job detail, not a separate route.

**`GET /output` returns the entire file every poll, not a delta.** Replace the content;
appending would duplicate the whole document every 3 seconds. Use `<pre>` with
`white-space: pre-wrap` in a scroll container — not `<textarea>`, which is for editing and
will fight you on selection and re-render.

Preserve scroll position across updates. Auto-scroll to the bottom **only** when the user is
already pinned there; otherwise keep `scrollTop` where they left it. Otherwise reading a
finished section yanks you away every 3 seconds.

While processing: `Updating while the job runs · last update 04:18:02`. Rendering markdown is
out of scope for v1. Offer `Copy`.

### Outline (curriculum)

When `outline` is present, render it — this is the structure the whole full-mode design turns
on, and seeing it is how you tell whether the model got it right.

```
01  Relational databases        Depends on  —
02  Transactions                Depends on  Relational databases
03  Locking and concurrency     Depends on  Transactions
04  Isolation levels            Depends on  Transactions, Locking and concurrency
```

Small rectangular chips for dependencies if you like; not pills. When `chapters` is populated,
mark which are written and show their `established` terms on expand.

## Acceptance

All of it verified. The backend half is held by `tests/` (`uv run pytest`); the browser half
was walked with throwaway Playwright scripts against a stubbed `llm`, which are **not**
committed — a JS test runner would be a dependency the constraints above rule out.

- [x] `cd frontend && npm install && npm run dev` works against `uv run fastapi dev`
- [x] Submit a PDF, watch `queued → processing → completed` without a refresh
- [x] OCR stage advances page by page; `Refine` appears only when `action !== "skip"`
- [x] Curriculum **short** job shows material/references and **never** `chapters`
- [x] Curriculum **full** job shows `chapters N/total` and **never** material/references
- [x] Output grows while the job runs, with no duplicated content
- [x] Scrolling up in the output is not undone by the next poll
- [x] Polling **stops** once a job is terminal — confirm in devtools Network
- [x] Kill the backend mid-job: data goes stale with a note, recovers on return
- [x] Retry a failed curriculum job — same id, resumes at the next chapter
- [x] Delete a running job → inline note, not a raw error
- [x] Ollama stopped → amber bar, submits disabled
- [x] Two jobs back to back → second reads as waiting for the worker
- [x] Rail header reads `1 running · N waiting`, never a combined "active" count
- [x] No fabricated ETA anywhere

## Standing backend gaps

**The big one is closed:** `tests/` now covers both pipelines end to end, resume, the OCR
cache, the 409s, the repository rules and the catalogue. It stubs `app.core.llm` and runs
the real app through `TestClient`, so the worker actually executes queued jobs. CLAUDE.md
documents the fixtures.

Still open, and each of them deliberate for now:

| Gap | Where it stands |
|---|---|
| Retrying a slide job restarts OCR from page one | Only after a crash *mid*-OCR. A run that finished is reused through the content-hash cache, so the common retry is cheap. Per-page checkpointing would close it. |
| A crashed chapter leaves an orphaned `chapters/NN.md` | Ignored on resume — `job.json` is the authority — but never cleaned up. |
| There is no cancel | On purpose: `delete` refuses a live job rather than pulling files out from under the worker. |
| The single-worker requirement is documented, not enforced | `--workers 2` silently creates two queues feeding one GPU. |
| The model list goes stale as Ollama ships models | Now `config/models.toml`, yours and gitignored, with `config/model_default.toml` as the checked-in starting point. |
