# study-ai-tools

Offline AI toolkit that turns slides into structured documents and curricula into study
material, powered by Ollama. Job-based: submit, get an id, poll, read the output.

See [CLAUDE.md](CLAUDE.md) for architecture and invariants, [TODO.md](TODO.md) for the next build.

## Requirements

- Python 3.14 (defined in `.python-version`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Ollama](https://ollama.com), running
- LibreOffice — optional, only for `.pptx` input

## Running

```sh
uv sync
uv run fastapi dev
```

Set `OLLAMA_HOST` / `OLLAMA_API_KEY` to use a remote Ollama. Cloud models are just model
names ending in `-cloud`. Run a **single** worker — the job queue lives in the process.

## CLI

Calls the services directly. Missing flags prompt interactively.

```sh
uv run python -m app.cli slides deck.pdf --action deep
uv run python -m app.cli curriculum syllabus.txt --mode full --no-plan
uv run python -m app.cli curriculum --resume 20260822150001-7b2c
```

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--dpi` | slides | Render resolution, default `200` |
| `--ocr-model` / `--refine-model` | slides | Skip the model prompts |
| `--action` | slides | `skip` \| `clean` \| `summary` \| `deep` |
| `--level` | slides | `beginner` \| `intermediate` \| `advanced` |
| `--mode` | curriculum | `short` \| `full` |
| `--no-plan` | curriculum | Generate the plan but keep it out of the document |
| `--skip-quiz` | curriculum | Skip the familiarity questions |
| `--resume <job-id>` | both | Re-run an existing job instead of creating one |
| `--lang` | both | Output language code, default `auto` |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Ollama reachable, LibreOffice present |
| `GET` | `/api/config` | Languages, audiences, actions, modes |
| `GET` | `/api/models` | Installed models with their roles |
| `GET` | `/api/jobs` | Every job, newest first |
| `POST` | `/api/slide-summarizer/jobs` | Multipart upload → `202` + job |
| `POST` | `/api/curriculum-generator/quiz` | Familiarity questions |
| `POST` | `/api/curriculum-generator/jobs` | → `202` + job |
| `GET` | `/api/{service}/jobs/{id}` | Status and progress |
| `GET` | `/api/{service}/jobs/{id}/output` | Output text, partial while running |
| `POST` | `/api/{service}/jobs/{id}/retry` | Re-run an existing job in place |
| `DELETE` | `/api/{service}/jobs/{id}` | Remove the job and its directory |

Uploads are capped at 200 MB and streamed to disk, so an oversized one is rejected while
it arrives. Retrying or deleting a job that is `queued` or `processing` returns `409` —
there is no cancel, so the only safe answer is to wait.

## Jobs

One directory per job, holding the record and every file the run produced.

```
data/jobs/slide_summarizer/<id>/       job.json  input.pdf|pptx  converted.pdf  raw.txt  output.md
data/jobs/curriculum_generator/<id>/   job.json  input.txt  plan.md  chapters/NN.md  output.md
```

Status moves `queued → processing → completed | failed`. Full-mode chapters are checkpointed
as they finish, so retrying an interrupted job (`--resume`, or `POST .../retry`) picks up from
the next chapter rather than starting over. Retrying a slide job re-runs its OCR.

OCR transcripts are reused across jobs keyed on the SHA-256 of the uploaded file plus the model
and dpi — two different decks both named `lecture.pdf` do not collide.

### Slide modes

| Mode | Output |
|------|--------|
| `skip` | Raw OCR only |
| `clean` | Fix OCR noise, broken words, grammar |
| `summary` | Bullet-point study notes |
| `deep` | Book-style structured document with prose and analogies |

### Curriculum modes

| Mode | Output |
|------|--------|
| `short` | Condensed material over all topics in one pass, plus further references |
| `full` | One chapter per topic, one model call each, chained through real dependencies |

The study plan is always generated — it produces the chapter order. `--no-plan` keeps it out
of the document without skipping it.

## Models

`config/models.toml` maps model names to roles (`vision`, `refine`, `llm`) and `local`/`cloud`.
**That file is yours and is gitignored — expand it as you pull models.** The checked-in
`config/model_default.toml` is the starting point and is used when you have not written a
`models.toml` yet; copy it across to begin:

```sh
cp config/model_default.toml config/models.toml
```

An unlisted model is still usable if you name it explicitly, but it is not *suggested* for any
role: unknown capability is not the same as supporting everything, and offering a text-only
model as an OCR choice is worse than offering nothing.

## Languages

`auto` preserves the source language. Otherwise: `ar` `de` `en` `es` `fi` `fr` `hi` `id` `it`
`ja` `ko` `nl` `pl` `pt` `ru` `sv` `th` `tr` `uk` `vi` `zh`. Quality on the less common ones
depends on the model's proficiency.
