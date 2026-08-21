from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.core import documents
from app.models.slide_summarizer import (
    AudienceLevel,
    RefineAction,
    SlideSummarizerJob,
    SlideSummarizerParams,
)
from app.services.slide_summarizer import SlideSummarizerService
from app.worker import enqueue

router = APIRouter(prefix="/api/slide-summarizer", tags=["slide-summarizer"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

service = SlideSummarizerService()


@router.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    ocr_model: str = Form(...),
    action: RefineAction = Form("skip"),
    refine_model: str | None = Form(None),
    lang: str = Form("auto"),
    level: AudienceLevel | None = Form(None),
    dpi: int = Form(200),
) -> SlideSummarizerJob:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".pptx"):
        raise HTTPException(400, "only .pdf and .pptx uploads are supported")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file exceeds the 200 MB limit")

    params = SlideSummarizerParams(
        filename=file.filename,
        source_format=suffix.lstrip("."),
        dpi=dpi,
        ocr_model=ocr_model,
        action=action,
        refine_model=refine_model,
        lang=lang,
        level=level,
    )

    try:
        job = service.create(params, content)
    except documents.DocumentError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    enqueue("slide_summarizer", job.id)
    return job


@router.get("/jobs")
async def list_jobs() -> list[SlideSummarizerJob]:
    return service.select_all()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> SlideSummarizerJob:
    job = service.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    return job


@router.get("/jobs/{job_id}/output")
async def get_output(job_id: str) -> dict:
    try:
        return {"id": job_id, "content": service.output(job_id)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> Response:
    if service.get(job_id) is None:
        raise HTTPException(404, f"no such job: {job_id}")
    service.delete(job_id)
    return Response(status_code=204)
