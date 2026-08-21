# study-ai-tools

Offline AI toolkit. Two pipelines — slides → OCR → refined document, and curriculum →
study plan → textbook — both run as **background jobs** against a local Ollama.

Submit → get a job id → a single FIFO worker executes it → poll for status → read output.
No streaming to the client, no event log. Closing the tab abandons the view, not the run.

## Design stance

**Write the obvious version.** A previous implementation of this system (tag `legacy-web`)
used a JSONL event log, SSE replay cursors, and subscriber index de-duplication; it was
rejected as too complicated and replaced with polling a status field in a JSON file. This
is a solo offline tool, not a distributed system. Machinery that buys resilience the
project doesn't need is a cost.

Prefer a file on disk over an in-memory registry, polling over streaming, one obvious code
path over a configurable one. Reuse an existing directory or record as state rather than
inventing a parallel one. If a design needs a paragraph to explain why it's correct,
propose the dumber version first.

## Layout

```
main.py              FastAPI app + lifespan (starts/stops the worker)
config/models.toml   model → roles + local/cloud
app/
  models/            Pydantic records (job schema, params, results)
  repositories/      job.json persistence — generic JobRepository[T] + two thin subclasses
  services/          the pipelines; the layer both the API and CLI call
  routers/           HTTP only — validate, delegate, map exceptions to status codes
  core/              llm, catalogue, languages, documents, paths, prompts/
  worker.py          one asyncio.Queue + one worker task
  cli.py             argparse, calls services directly (no HTTP, no worker)
frontend/            React + Vite UI — plain React, four dependencies, no API client
  dist/              the build main.py mounts at / (gitignored)
  src/api.js         one hand-written function per endpoint
  src/usePolling.js  the only polling primitive
  src/components/    shell, the two forms, the jobs rail, job detail
```

Dependency direction is one-way: `routers → services → repositories → models`, with `core`
available to all. A repository never imports a service; a service never imports a router.

## Invariants

Break these and things quietly rot.

| Invariant | Why |
|---|---|
| **`job.json` is the resume authority, not files on disk.** `job.chapters` lists finished chapters; a stray `chapters/03.md` from a crash is ignored and overwritten. | A half-written file must never look complete. |
| **`params` is immutable after `create()`; `result` is written at completion.** | `params` is what the user asked for. Mutating it loses the record of that. |
| **`input_path` / `output_path` are relative to the job directory.** | Keeps `job.json` portable and makes the path-traversal check one line (`repository.resolve()`). |
| **Every stored model is `extra="forbid"`.** | Catches drift. See the migration note below. |
| **Blocking work goes through `asyncio.to_thread`.** | The worker shares the event loop with the API. A synchronous `subprocess.run` freezes every request, including polling the job it is running. |
| **One uvicorn worker.** | The queue lives in the process. `--workers 2` silently creates two queues feeding one GPU. |
| **The OCR cache keys on `source_sha256`, never `filename`.** | Two people uploading `lecture.pdf` are not uploading the same lecture. |
| **`MATERIAL_TOPIC_STABLE` must be byte-identical across every chapter of a job.** | Ollama's prompt prefix cache only hits on an exact prefix match. Putting anything varying above it silently doubles the cost of full mode. |
| **`catalogue.for_role()` returns only explicitly classified models.** | An unknown model is an unknown capability. Offering a text-only model as an OCR choice is worse than offering nothing. |

### Schema migration

`extra="forbid"` plus records already on disk means **adding a required field breaks every
existing job**: `select_all()` will log a warning and skip them. Give new fields a default.
If a genuinely breaking change is needed, either write a migration over `data/jobs/*/job.json`
or accept that old jobs become unreadable — and say which.

## The pipelines

**Slides** (`app/services/slide_summarizer.py`). `convert` (PPTX only, LibreOffice) → `ocr`
(per page, appending to `raw.txt`) → `refine` (streams into `output.md`). A page that fails
OCR becomes `[missing page N]` rather than killing the run. `action="skip"` stops after
`raw.txt`.

**Curriculum** (`app/services/curriculum_generator.py`). `metadata` → `plan` → `outline` →
then `short` (one material pass + references) or `full` (one call per chapter).

Full mode is the subtle one. It makes **exactly one model call per chapter**:

- The `outline` stage distills the plan once into `{topic, scope, depends_on}` per chapter,
  so the raw curriculum is never resent.
- `depends_on` names earlier topics only and is `[]` when a chapter stands alone. Deciding
  this once, with every topic visible, is what stops adjacent chapters being dragged
  together. A chapter is *told* whether a link exists — it never guesses. `_prune_dependencies()`
  drops forward references and invented topics, because models emit both.
- Each chapter closes with `<!-- established: term; term -->`, stripped before saving and
  stored in `job.chapters[].established`. This replaces a second summarization call per
  chapter, and keeps the ledger flat instead of growing with chapter count.
- The study plan is **always** generated — it produces the chapter order. `include_plan`
  only controls whether it reaches the document.

Prompts in `app/core/prompts/` are lifted from the original CLI and are the actual product
value. Don't casually reword them; changing output structure means changing parsing too.

## The frontend

Built to [TODO.md](TODO.md), which stays the spec. It polls; there is no SSE and no
websocket to add back.

| Rule | Why |
|---|---|
| **Polling stops when a job is terminal.** The detail's interval drops to 0 on `completed`/`failed`; the rail keeps polling because jobs also arrive from the CLI. | A loop that never stops is the main way this UI can go wrong. |
| **Stage checklists are derived from `params.mode` / `params.action`**, never from a list of every stage name. | `material`+`references` and `chapters` are branches. A job must never show both. |
| **`GET /output` returns the whole file, so the content is replaced.** | Appending would duplicate the document every 3 seconds. |
| **A finished job is described by what it left behind**, not by `progress`. | The repository clears `progress` on completion, so counts come from `result.pages` / `chapters` vs `outline`. |
| **URLs are hyphenated (`/api/slide-summarizer`), the `service` field is not (`slide_summarizer`).** `api.js` owns the one mapping. | The merged job list returns records whose `service` cannot be dropped into a URL. |

Connection loss never blanks the screen: the last data stays, marked stale after three
consecutive failures, and polling keeps retrying.

## Testing

**There are no committed tests yet.** Everything was verified once by hand with throwaway
scripts that were never checked in — the backend by hand, the frontend by driving it with
Playwright against a stubbed `llm`. [TODO.md](TODO.md) holds the frontend's acceptance list
and this remains the standing gap.

Stub the `llm` module rather than mocking Ollama; services call it by module reference, so
patching the attributes works regardless of import order:

```python
from app.core import llm
async def fake_complete(*, model, messages, options=None, think=None): ...
async def fake_stream(*, model, messages, options=None, think=None): yield "text"
llm.complete, llm.stream_chat = fake_complete, fake_stream
```

`TestClient(main.app)` runs the real lifespan, so the worker actually executes queued jobs —
poll the job endpoint until terminal. Set `PYTHONPATH` to the repo root; `uv run` must be
invoked from the project directory or it won't find the venv.

Real PDFs are cheap to make: `pypdfium2.PdfDocument.new()`, `new_page(w, h)`, `save(path)`.
Use *different* page sizes per fixture, or the content-hash OCR cache will make the second
job a no-op and quietly invalidate the test.

## Running

```sh
uv sync
uv run fastapi dev
uv run python -m app.cli curriculum syllabus.txt --mode full --no-plan
uv run python -m app.cli curriculum --resume <job-id>
cd frontend && npm install && npm run build  # then fastapi serves the UI at :8000
cd frontend && npm run dev                   # :5173, proxies /api — for UI work only
```

`main.py` mounts `frontend/dist` at `/` when it exists, so a built UI needs one process.
The mount is guarded: `dist/` is gitignored, and a fresh clone must still start.

`OLLAMA_HOST` / `OLLAMA_API_KEY` point at a remote Ollama. Cloud models are just names
ending `-cloud` or `:cloud`. LibreOffice is optional and only needed for `.pptx`.

## History

| Tag | What it holds |
|---|---|
| `legacy-cli` | The original interactive CLI scripts. Source of every prompt. |
| `legacy-web` | FastAPI + SSE era with a React UI, including the job-aware components. Reference for the frontend rewrite; its job machinery was deliberately not carried forward. |
