import asyncio

from fastapi import APIRouter

from app.core import codex
from app.models.settings import Settings
from app.services.settings import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])

service = SettingsService()


async def _view(settings: Settings) -> dict:
    """The stored settings plus what the Codex CLI reports, read live on every request:
    `codex login` and plan changes happen outside the app."""
    # Three separate CLI processes, so they run side by side rather than one after another.
    login, models, usage = await asyncio.gather(
        codex.login_status(), codex.list_models(), codex.usage(), return_exceptions=True,
    )
    for result in (login, models, usage):
        if isinstance(result, BaseException) and not isinstance(result, codex.CodexError):
            raise result
    models_error = str(models) if isinstance(models, codex.CodexError) else None
    usage_error = str(usage) if isinstance(usage, codex.CodexError) else None
    return {
        **settings.model_dump(),
        "codex_login": login,
        "codex_models": [] if models_error else models,
        "codex_models_error": models_error,
        "codex_usage": None if usage_error else usage,
        "codex_usage_error": usage_error,
    }


@router.get("")
async def get_settings() -> dict:
    return await _view(service.get())


@router.put("")
async def put_settings(settings: Settings) -> dict:
    return await _view(service.update(settings))
