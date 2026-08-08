#!/usr/bin/env python3
"""study-ai-tools web app — one server for both the API and the React UI.

    uvicorn main:app --reload

Generation is job-based: a POST to a `/jobs` endpoint queues the run and returns
an id, a background worker executes it, and clients watch through the
Server-Sent Events stream at `/api/jobs/{id}/events`. Watching is detachable —
closing the tab abandons the view, not the run.

Because the job registry lives in this process, the server must run a *single*
worker. `--reload` restarting mid-run marks the in-flight job `interrupted`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from core import events as ev
from core import jobs, llm, slides, storage, study_plan
from core.languages import audience_options, language_options
from core.paths import FRONTEND_DIST, INPUT_DIR

STUDY_PLAN_TOOL = "study-plan-generatinator"
SLIDES_TOOL = "slide-summarizinator"


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.register(STUDY_PLAN_TOOL, _study_plan_pipeline)
    jobs.register(SLIDES_TOOL, _slides_pipeline)
    await jobs.startup()
    try:
        yield
    finally:
        await jobs.shutdown()


app = FastAPI(title="study-ai-tools", version="1.0.0", lifespan=lifespan)

# Only needed when running the Vite dev server on :5173 against this backend.
# In the unified build the UI is same-origin and this never comes into play.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


# ── SSE plumbing ──────────────────────────────────────────────────────────────

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # tell any proxy in front of us not to buffer
}


async def _to_sse(source: AsyncIterator[ev.StreamEvent]) -> AsyncIterator[str]:
    """Render an event source as SSE frames, turning a crash into an `error` event."""
    yield ": stream open\n\n"  # flushes headers so the browser starts reading
    try:
        async for event in source:
            yield event.to_sse()
    except asyncio.CancelledError:
        # the client navigated away — this only abandons the view; the job keeps
        # running under the worker and can be reattached later
        raise
    except Exception as e:
        yield ev.error(f"{type(e).__name__}: {e}").to_sse()


def sse_response(source: AsyncIterator[ev.StreamEvent]) -> StreamingResponse:
    return StreamingResponse(_to_sse(source), media_type="text/event-stream",
                             headers=SSE_HEADERS)


# ── request bodies ────────────────────────────────────────────────────────────

class AssessmentRequest(BaseModel):
    curriculum: str = Field(min_length=1)
    model: str = Field(min_length=1)


class Answer(BaseModel):
    id: Any
    known: bool


class StudyPlanRequest(BaseModel):
    curriculum: str = Field(min_length=1)
    model: str = Field(min_length=1)
    lang: str = "auto"
    mode: Literal["plan", "full", "book"] = "plan"
    source_name: str = "curriculum.txt"
    questions: list[dict] = []
    answers: list[Answer] = []
    use_cache: bool = True
    fresh: bool = False


class SlidesRequest(BaseModel):
    file: str = Field(min_length=1, description="PDF filename inside inputs/")
    ocr_model: str = Field(min_length=1)
    action: Literal["skip", "clean", "summary", "deep"] = "skip"
    refine_model: str | None = None
    lang: str = "auto"
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    dpi: int = Field(default=200, ge=50, le=600)
    use_cache: bool = True


# ── metadata ──────────────────────────────────────────────────────────────────

@api.get("/health")
async def health() -> dict:
    try:
        await llm.list_models()
        ollama = "up"
    except llm.LLMError:
        ollama = "down"
    return {"status": "ok", "ollama": ollama, "frontend_built": FRONTEND_DIST.is_dir()}


@api.get("/config")
async def config() -> dict:
    return {
        "languages": language_options(),
        "audiences": audience_options(),
        "modes": [
            {"value": "plan", "label": "Plan",
             "description": "Study plan only — fastest."},
            {"value": "full", "label": "Full",
             "description": "Study plan plus material for every topic in one pass."},
            {"value": "book", "label": "Book",
             "description": "Study plan plus one chained chapter per topic. Slow, but "
                            "checkpointed after every chapter — closing the tab is safe."},
        ],
        "actions": [
            {"value": "skip", "label": "Skip", "description": "Save the raw OCR only."},
            {"value": "clean", "label": "Clean", "description": "Fix OCR noise, broken words, grammar."},
            {"value": "summary", "label": "Summary", "description": "Compress into bullet-point study notes."},
            {"value": "deep", "label": "Deep", "description": "Book-style structured document with prose."},
        ],
    }


@api.get("/models")
async def models() -> dict:
    try:
        return {
            "llm": await study_plan.list_models(),
            "vision": await slides.list_vision_models(),
            "refine": await slides.list_refine_models(),
            "all": await llm.list_models(),
        }
    except llm.LLMError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


# ── study plan ────────────────────────────────────────────────────────────────

@api.post("/study-plan/assessment")
async def study_plan_assessment(body: AssessmentRequest) -> dict:
    """Familiarity questions to calibrate the plan. Answers go to /stream."""
    try:
        _, topics, metadata = await study_plan.extract_metadata(
            body.curriculum, body.model, "plan",
        )
        questions = await study_plan.build_assessment(body.curriculum, topics, body.model)
    except llm.LLMError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"topics": topics, "questions": questions,
            "course": metadata.get("course", ""), "title": metadata.get("title", "")}


@api.get("/study-plan/partial")
async def study_plan_partial(source_name: str, model: str, lang: str) -> dict:
    """Whether an interrupted book run can be resumed for this source/model/lang."""
    return {"partial": storage.peek_partial(source_name, model, lang)}


@api.post("/study-plan/jobs", status_code=202)
async def study_plan_job(body: StudyPlanRequest) -> dict:
    """Queue a curriculum run. Watch it at /api/jobs/{id}/events."""
    known_ids = [a.id for a in body.answers if a.known]
    summary = study_plan.summarize_assessment(body.questions, known_ids) if body.questions else ""

    return jobs.submit(
        STUDY_PLAN_TOOL,
        {
            "raw": body.curriculum.strip(),
            "source_name": body.source_name,
            "model": body.model,
            "lang": body.lang,
            "mode": body.mode,
            "assessment_summary": summary,
            "use_cache": body.use_cache,
            "fresh": body.fresh,
        },
        label=f"{body.source_name} · {body.mode} · {body.model}",
    )


def _study_plan_pipeline(params: dict) -> AsyncIterator[ev.StreamEvent]:
    return study_plan.generate(**params)


# ── slides ────────────────────────────────────────────────────────────────────

@api.get("/slides/inputs")
async def slides_inputs() -> dict:
    if not INPUT_DIR.exists():
        return {"files": []}
    files = [
        {"name": p.name, "size": p.stat().st_size}
        for p in sorted(INPUT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    return {"files": files}


@api.post("/slides/upload")
async def slides_upload(file: UploadFile) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf uploads are supported")

    target = storage.unique_input_path(file.filename)
    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="PDF exceeds the 200 MB limit")
            out.write(chunk)

    return {"name": target.name, "size": size}


@api.post("/slides/jobs", status_code=202)
async def slides_job(body: SlidesRequest) -> dict:
    """Queue a PDF run. Watch it at /api/jobs/{id}/events."""
    try:
        _resolve_input(body.file)  # fail loudly now rather than inside the worker
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return jobs.submit(
        SLIDES_TOOL,
        {
            "file": body.file,
            "ocr_model": body.ocr_model,
            "action": body.action,
            "refine_model": body.refine_model,
            "lang": body.lang,
            "level": body.level,
            "dpi": body.dpi,
            "use_cache": body.use_cache,
        },
        label=f"{body.file} · {body.action} · {body.ocr_model}",
    )


def _slides_pipeline(params: dict) -> AsyncIterator[ev.StreamEvent]:
    # stored as a bare filename so the record stays JSON-serializable
    params = dict(params)
    return slides.generate(pdf_path=_resolve_input(params.pop("file")), **params)


def _resolve_input(name: str) -> Path:
    """Resolve a filename to a PDF inside inputs/, refusing anything outside it."""
    path = (INPUT_DIR / name).resolve()
    if path.parent != INPUT_DIR.resolve() or not path.is_file():
        raise FileNotFoundError(f"no such input file: {name}")
    return path


# ── jobs ──────────────────────────────────────────────────────────────────────

@api.get("/jobs")
async def jobs_list(tool: str | None = None) -> dict:
    return {"jobs": jobs.listing(tool)}


@api.get("/jobs/{job_id}")
async def job_detail(job_id: str) -> dict:
    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return record


@api.get("/jobs/{job_id}/events")
async def job_events(job_id: str, from_: int = Query(0, alias="from")) -> StreamingResponse:
    """Replay this job's events from `from`, then follow it live until it ends.

    Detaching is free: the run belongs to the worker, not to this request.
    """
    if jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return sse_response(jobs.stream(job_id, max(0, from_)))


@api.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: str) -> dict:
    try:
        return jobs.cancel(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}") from e


@api.delete("/jobs/{job_id}", status_code=204)
async def job_delete(job_id: str) -> Response:
    try:
        jobs.delete(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return Response(status_code=204)


# ── outputs ───────────────────────────────────────────────────────────────────

@api.get("/outputs")
async def outputs() -> dict:
    return {"outputs": storage.list_outputs()}


@api.get("/outputs/{tool}/{name}")
async def output_file(tool: str, name: str, download: bool = False):
    try:
        path = storage.resolve_output(tool, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if download:
        return FileResponse(path, filename=name, media_type="application/octet-stream")
    return JSONResponse({"name": name, "tool": tool,
                         "content": path.read_text(encoding="utf-8")})


app.include_router(api)


# ── the React app, served by this same process ────────────────────────────────

class SPAStaticFiles(StaticFiles):
    """Static files with a client-side-routing fallback to index.html.

    Starlette signals a miss by *raising* 404, so reloading a deep link would
    otherwise land on an API error page instead of the React app. Unknown
    /api/* paths keep their 404 — only UI routes fall back.
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and not path.startswith("api/"):
            return await super().get_response("index.html", scope)
        return response


if FRONTEND_DIST.is_dir():
    # mounted last so every /api/* route above wins the match
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/")
    async def frontend_missing() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The React frontend has not been built yet.",
                "fix": "cd frontend && npm install && npm run build",
                "expected_at": str(FRONTEND_DIST),
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
