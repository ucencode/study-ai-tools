import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import Field

from app.core import documents
from app.core.paths import TMP_DIR
from app.models._job import Strict
from app.models.preset import Preset
from app.models.slide_summarizer import (
    AudienceLevel,
    RefineAction,
    SlideSummarizerJob,
    SlideSummarizerParams,
    SlideSummarizerSettings,
)
from app.services.preset import MAX_NAME, SLIDE_PRESETS
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

    # Spool to disk in bounded memory and stop reading the moment the cap is crossed,
    # rather than materializing the whole body and only then deciding to reject it.
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    staged = TMP_DIR / f"upload-{secrets.token_hex(8)}{suffix}"
    try:
        size = 0
        with staged.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "file exceeds the 200 MB limit")
                out.write(chunk)

        job = service.create(params, staged)
    except documents.DocumentError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        staged.unlink(missing_ok=True)

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


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str) -> SlideSummarizerJob:
    """Re-run a job in place. OCR restarts, but the job directory and its id are kept."""
    job = service.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    if job.status in ("queued", "processing"):
        raise HTTPException(409, f"job {job_id} is already {job.status}")

    job = service.repository.set_status(job_id, "queued")
    enqueue("slide_summarizer", job_id)
    return job


@router.get("/jobs/{job_id}/output")
async def get_output(job_id: str) -> dict:
    try:
        return {"id": job_id, "content": service.output(job_id)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> Response:
    job = service.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    if job.status in ("queued", "processing"):
        # There is deliberately no cancel, so the only safe answer is to say no:
        # rmtree under a running job pulls files out from beneath the worker.
        raise HTTPException(409, f"job {job_id} is {job.status} — wait for it to finish")
    service.delete(job_id)
    return Response(status_code=204)


class PresetRequest(Strict):
    name: str = Field(min_length=1, max_length=MAX_NAME)
    settings: SlideSummarizerSettings


@router.get("/presets")
async def list_presets() -> list[Preset[SlideSummarizerSettings]]:
    return SLIDE_PRESETS.list()


@router.post("/presets")
async def save_preset(body: PresetRequest) -> Preset[SlideSummarizerSettings]:
    """Create, or overwrite the preset of the same name."""
    try:
        return SLIDE_PRESETS.save(body.name, body.settings)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: str) -> Response:
    try:
        SLIDE_PRESETS.delete(preset_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)
