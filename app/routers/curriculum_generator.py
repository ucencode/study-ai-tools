from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.core import llm
from app.models._job import Strict
from app.models.curriculum_generator import (
    Answer,
    CurriculumGeneratorJob,
    CurriculumGeneratorParams,
    CurriculumGeneratorSettings,
    GenerationMode,
    Question,
)
from app.models.preset import Preset
from app.services.curriculum_generator import CurriculumGeneratorService
from app.services.preset import CURRICULUM_PRESETS, MAX_NAME
from app.worker import enqueue

router = APIRouter(prefix="/api/curriculum-generator", tags=["curriculum-generator"])

service = CurriculumGeneratorService()


class QuizRequest(BaseModel):
    curriculum: str = Field(min_length=1)
    model: str = Field(min_length=1)


class JobRequest(BaseModel):
    curriculum: str = Field(min_length=1)
    model: str = Field(min_length=1)
    # Empty is meaningful: the reader named nothing, so views fall back to the course
    # name the metadata stage reads out of the curriculum.
    source_name: str = ""
    lang: str = "auto"
    mode: GenerationMode = "short"
    include_plan: bool = True
    topic_context: dict[str, str] = {}
    questions: list[Question] = []
    answers: list[Answer] = []


@router.post("/quiz")
async def quiz(body: QuizRequest) -> dict:
    """Familiarity questions. Answer them, then pass both back to POST /jobs."""
    try:
        return await service.build_quiz(body.curriculum, body.model)
    except llm.LLMError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/jobs", status_code=202)
async def create_job(body: JobRequest) -> CurriculumGeneratorJob:
    params = CurriculumGeneratorParams(
        source_name=body.source_name,
        model=body.model,
        lang=body.lang,
        mode=body.mode,
        include_plan=body.include_plan,
        topic_context=body.topic_context,
        questions=body.questions,
        answers=body.answers,
    )
    job = service.create(params, body.curriculum)
    enqueue("curriculum_generator", job.id)
    return job


@router.get("/jobs")
async def list_jobs() -> list[CurriculumGeneratorJob]:
    return service.select_all()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> CurriculumGeneratorJob:
    job = service.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    return job


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str) -> CurriculumGeneratorJob:
    """Continue a job in place, picking up from its last finished chapter."""
    job = service.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    if job.status in ("queued", "processing"):
        raise HTTPException(409, f"job {job_id} is already {job.status}")

    job = service.repository.set_status(job_id, "queued")
    enqueue("curriculum_generator", job_id)
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
    settings: CurriculumGeneratorSettings


@router.get("/presets")
async def list_presets() -> list[Preset[CurriculumGeneratorSettings]]:
    return CURRICULUM_PRESETS.list()


@router.post("/presets")
async def save_preset(body: PresetRequest) -> Preset[CurriculumGeneratorSettings]:
    """Create, or overwrite the preset of the same name."""
    try:
        return CURRICULUM_PRESETS.save(body.name, body.settings)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: str) -> Response:
    try:
        CURRICULUM_PRESETS.delete(preset_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)
