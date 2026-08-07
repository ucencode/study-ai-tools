# study-ai-tools

Offline AI toolkit for converting PDFs and slides into structured documents and self-study material, powered by Ollama and local LLMs.

Runs as a **local web app** (FastAPI + React) or straight from the **terminal** — both drive the same generation code in `core/`, and both stream tokens as the model produces them.

## Project Structure

```
study-ai-tools/
├── main.py               # FastAPI app: SSE API + serves the built React UI at /
├── core/                 # the AI pipelines — async generators, no UI assumptions
│   ├── events.py         # StreamEvent + SSE framing
│   ├── llm.py            # async Ollama client
│   ├── languages.py      # language / audience vocabulary
│   ├── prompts_*.py      # system + user prompts
│   ├── slides.py         # PDF → OCR → refined document
│   ├── study_plan.py     # curriculum → plan / material / book
│   └── storage.py        # outputs, caching, resumable state
├── frontend/             # Vite + React UI (build output in frontend/dist)
├── inputs/               # drop PDF and curriculum .txt files here
├── outputs/
│   ├── slide-summarizinator/      # raw + compiled OCR outputs
│   └── study-plan-generatinator/  # generated study plans and materials
├── tools/                # CLI front-ends over core/
│   ├── slide-summarizinator/      # index.py, batch.py, preset-generator.py
│   └── study-plan-generatinator/  # index.py
├── requirements.txt
└── setup.sh
```

## Requirements

- Python 3.11+
- Node 18+ (only to build the web UI)
- [Ollama](https://ollama.com) installed and running
- poppler on `PATH` for PDF rendering — `apt install poppler-utils` / `brew install poppler`

## Setup

```bash
./setup.sh
```

Or by hand:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

---

## Web app

One process serves both the React UI and the API:

```bash
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The three tabs map to the two tools plus a browser for everything you've generated:

| Tab | What it does |
|-----|--------------|
| Study Plan | Paste or load a curriculum, optionally answer a familiarity check, stream a plan / material / book |
| Slides | Upload a PDF, pick a vision model and refine mode, watch pages transcribe and the document stream in |
| Outputs | Read and download every file the tools have written |

Output still lands in `outputs/`, exactly as the CLIs write it — the web UI is another way in, not a separate store.

### Working on the UI

`npm run dev` gives hot reload on <http://localhost:5173> and proxies `/api` to uvicorn on `:8000`, so run both:

```bash
uvicorn main:app --reload          # terminal 1
cd frontend && npm run dev         # terminal 2
```

Rebuild (`npm run build`) when you're done, so the single-server setup picks the changes up.

### API

Generation endpoints stream [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events). They're `POST` (the request bodies carry whole curricula), so the frontend reads them with `fetch` + a `ReadableStream` reader rather than `EventSource`.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/health` | Server status and whether Ollama answers |
| `GET` | `/api/config` | Languages, audience levels, modes, refine actions |
| `GET` | `/api/models` | Installed models, split by role |
| `POST` | `/api/study-plan/assessment` | Familiarity questions for a curriculum |
| `GET` | `/api/study-plan/partial` | Whether an interrupted book run can resume |
| `POST` | `/api/study-plan/stream` | **SSE** — plan / material / book |
| `GET` | `/api/slides/inputs` | PDFs available in `inputs/` |
| `POST` | `/api/slides/upload` | Upload a PDF into `inputs/` |
| `POST` | `/api/slides/stream` | **SSE** — OCR and refine |
| `GET` | `/api/outputs` | Every generated file with its frontmatter |
| `GET` | `/api/outputs/{tool}/{name}` | Read one (`?download=true` to save it) |

Each SSE frame is a named event with a JSON payload:

```
event: token
data: {"text": "…the next chunk of generated text…"}
```

| Event | Payload |
|-------|---------|
| `status` | `{stage, message, …}` — progress, the same lines the CLI prints |
| `section` | `{key, label}` — a new output section begins (plan, chapter 3/12, …) |
| `token` | `{text}` — generated text, emitted as the model produces it |
| `meta` | frontmatter, topic lists |
| `done` | `{path, name, tool, …}` — a file was written |
| `error` | `{message}` — the run stopped |

Interactive docs are at `/docs` while the server is running.

---

## Tool 1 — OCR (`tools/slide-summarizinator/`)

Converts PDF pages to images, runs OCR via a vision model, and optionally refines the output into clean text, study notes, or structured book-style documents.

### Supported Models

| Role | Keywords matched |
|------|-----------------|
| Vision (OCR) | `qwen3.5`, `qwen3-vl`, `qwen2.5vl`, `deepseek-ocr`, `llama3.2-vision`, `gemma4`, `ministral-3`, `glm-ocr` |
| Refine (LLM) | `glm-5.1`, `gemma4`, `qwen3.5`, `gpt-oss` |

```bash
ollama pull glm-ocr:bf16
```

### Usage

**Interactive:**

```bash
python tools/slide-summarizinator/index.py inputs/slides.pdf
```

Prompts you to select vision model, refine mode, language, and audience level. Use shell tab completion on the file path.

**With preset (non-interactive):**

```bash
python tools/slide-summarizinator/index.py inputs/slides.pdf --preset example.toml
```

**Batch — process all PDFs in `inputs/`:**

```bash
python tools/slide-summarizinator/batch.py --preset example.toml
```

| Flag | Default | Description |
|------|---------|-------------|
| `--preset` | — | Optional, if its empty you will select one preset or create a new one |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--dpi` | `200` | Render resolution (higher = more detail, slower) |
| `--preset` | — | Load a TOML preset from `tools/slide-summarizinator/presets/`, skip interactive prompts |

### Presets

TOML files in `tools/slide-summarizinator/presets/`. See [`tools/slide-summarizinator/presets/example.toml`](tools/slide-summarizinator/presets/example.toml):

```toml
vision_model = "qwen3.5:9b"
refine_model = "gpt-oss:120b-cloud"
action = "deep"      # clean | summary | deep | skip
lang = "en"          # "auto" (preserve source language) or see supported languages below
level = "beginner"   # beginner | intermediate | advanced
```

Validation runs before processing — invalid models, actions, languages, or levels will exit with a clear error.

### Refine Modes

| Mode | Description |
|------|-------------|
| `skip` | Save raw OCR only |
| `clean` | Fix OCR noise, broken words, grammar |
| `summary` | Compress into bullet-point study notes |
| `deep` | Book-style structured document with prose and analogies |

### Output

```
outputs/slide-summarizinator/
  <timestamp>-raw.txt       # raw OCR text (file, pages, dpi, model)
  <timestamp>-compiled.txt  # refined output (origin, model, mode, lang, level)
```

Raw OCR results are cached per PDF filename and vision model. Re-running the same file with the same model skips OCR and reuses the cached output.

---

## Tool 2 — Learning Plan Generator (`tools/study-plan-generatinator/`)

Takes a curriculum `.txt` file and generates a structured self-study plan and per-topic study material using a local LLM.

### Supported Models

Any model matched by keywords: `llama3`, `qwen3`, `gemma`, `mistral`, `deepseek`, `phi`, `gpt-oss`

### Usage

**Interactive (picks curriculum file from `inputs/`):**

```bash
python tools/study-plan-generatinator/index.py
```

Prompts you to select a model, output language, and mode (plan only or plan + material).

**With arguments:**

```bash
python tools/study-plan-generatinator/index.py inputs/curriculum.txt --lang en --mode full
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | — | Skip model selection prompt |
| `--lang` | — | Output language code (see supported languages) |
| `--mode` | — | `plan` = study plan only \| `full` = plan + material per topic \| `book` = one chained chapter per topic |
| `--skip-assessment` | — | Skip the learner familiarity questions |
| `--fresh` | — | Book mode: discard an in-progress run and start over |

### Modes

| Mode | Output |
|------|--------|
| `plan` | Weekly schedule, phase breakdown, per-topic checkpoints, resource recommendations |
| `full` | Everything in `plan` + per-topic study material (concept, worked examples, practice problems, misconceptions, go deeper) |
| `book` | Everything in `plan` + one book-style chapter per topic, each chained onto a digest of the previous ones |

Book mode is slow (two model calls per chapter) but checkpoints after every chapter — interrupt it with Ctrl+C, or close the browser tab, and the next run offers to resume.

### Output

```
outputs/study-plan-generatinator/
  <timestamp>-<slug>-study_plan.md   # plan mode
  <timestamp>-<slug>-full.md         # full mode
  <timestamp>-<slug>-book.md         # book mode
```

All output files include YAML frontmatter (course, topics, credits, estimated weeks, model, language).

---

## Supported Languages (both tools)

| Code | Language |
|------|----------|
| `auto` | Preserve source language |
| `ar` | العربية (Arabic) |
| `de` | Deutsch (German) |
| `en` | English |
| `es` | Español (Spanish) |
| `fi` | Suomi (Finnish)* |
| `fr` | Français (French) |
| `hi` | हिन्दी (Hindi)* |
| `id` | Bahasa Indonesia |
| `it` | Italiano (Italian)* |
| `ja` | 日本語 (Japanese)* |
| `ko` | 한국어 (Korean)* |
| `nl` | Nederlands (Dutch)* |
| `pl` | Polski (Polish)* |
| `pt` | Português (Portuguese) |
| `ru` | Русский (Russian) |
| `sv` | Svenska (Swedish)* |
| `th` | ภาษาไทย (Thai)* |
| `tr` | Türkçe (Turkish)* |
| `uk` | Українська (Ukrainian)* |
| `vi` | Tiếng Việt (Vietnamese)* |
| `zh` | 简体中文 (Chinese) |

\* Output quality depends on the model's proficiency in this language.
