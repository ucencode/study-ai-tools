# study-ai-tools

Offline AI toolkit that turns slides into structured documents and curricula into study
material, powered by Ollama. Job-based: submit, get an id, poll, read the output.

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
| `DELETE` | `/api/{service}/jobs/{id}` | Remove the job and its directory |

## Jobs

One directory per job, holding the record and every file the run produced.

```
data/jobs/slide_summarizer/<id>/       job.json  input.pdf|pptx  converted.pdf  raw.txt  output.md
data/jobs/curriculum_generator/<id>/   job.json  input.txt  plan.md  chapters/NN.md  output.md
```

Status moves `queued → processing → completed | failed`. Full-mode chapters are checkpointed
as they finish, so re-running an interrupted job resumes from the next one.

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
It goes stale as Ollama ships new models — add entries as you pull them. Anything installed but
unlisted still works, it just has no role hints.

## Languages

`auto` preserves the source language. Otherwise: `ar` `de` `en` `es` `fi` `fr` `hi` `id` `it`
`ja` `ko` `nl` `pl` `pt` `ru` `sv` `th` `tr` `uk` `vi` `zh`. Quality on the less common ones
depends on the model's proficiency.
