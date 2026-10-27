from fastapi import APIRouter, HTTPException

from app.core import catalogue, codex, documents, llm
from app.core.languages import audience_options, language_options
from app.core.prompts.slide_summarizer import ACTIONS
from app.services.curriculum_generator import MODES
from app.services.settings import SettingsService
from app.worker import SERVICES, service

router = APIRouter(prefix="/api", tags=["meta"])

settings = SettingsService()


@router.get("/health")
async def health() -> dict:
    try:
        await llm.list_models()
        ollama = "up"
    except llm.LLMError:
        ollama = "down"
    return {
        "status": "ok",
        "ollama": ollama,
        "libreoffice": documents.libreoffice_available(),
    }


@router.get("/config")
async def config() -> dict:
    return {
        "languages": language_options(),
        "audiences": audience_options(),
        "actions": ACTIONS,
        "modes": MODES,
        "pptx_enabled": documents.libreoffice_available(),
    }


@router.get("/models")
async def models() -> dict:
    try:
        codex_models = await settings.codex_models()
    except codex.CodexError:
        # The Settings page shows why; the Ollama models are still worth offering.
        codex_models = []
    try:
        return {
            "models": await catalogue.available(codex_models),
            "vision": await catalogue.for_role("vision", codex_models),
            "refine": await catalogue.for_role("refine", codex_models),
            "llm": await catalogue.for_role("llm", codex_models),
        }
    except llm.LLMError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/jobs")
async def all_jobs(service_name: str | None = None) -> list[dict]:
    """Every job from both services, newest first."""
    names = [service_name] if service_name else list(SERVICES)
    jobs = []
    for name in names:
        if name not in SERVICES:
            raise HTTPException(404, f"unknown service: {name}")
        jobs += [job.model_dump() for job in service(name).select_all()]
    return sorted(jobs, key=lambda job: job["created_at"], reverse=True)
