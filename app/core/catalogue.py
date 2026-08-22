"""Which models can play which role, from config/models.toml.

The catalogue is a hint, not a whitelist. Anything Ollama has installed is usable;
listing it here only tells the UI what to offer for each role.
"""

import tomllib
from pathlib import Path

from app.core import llm
from app.core.paths import MODELS_DEFAULT_FILE, MODELS_FILE

ROLES = ("vision", "refine", "llm")


def _models_file() -> Path:
    """Your list if you have written one, otherwise the checked-in default.

    Resolved per read rather than at import, so creating config/models.toml takes
    effect without a restart — the same as editing it does.
    """
    return MODELS_FILE if MODELS_FILE.exists() else MODELS_DEFAULT_FILE


def _entries() -> list[dict]:
    path = _models_file()
    if not path.exists():
        return []
    with path.open("rb") as file:
        return tomllib.load(file).get("models", [])


def catalogue() -> dict[str, dict]:
    """Listed models keyed by name."""
    return {entry["name"]: entry for entry in _entries() if entry.get("name")}


async def available() -> list[dict]:
    """Every installed model, annotated with its listed roles.

    A model Ollama has but the config doesn't mention is still returned, marked
    `unlisted` with no roles — usable the day it lands, just without role hints.
    """
    listed = catalogue()
    installed = await llm.list_models()

    models = []
    for name in installed:
        entry = listed.get(name)
        models.append({
            "name": name,
            "roles": entry.get("roles", []) if entry else [],
            "where": entry.get("where", "local") if entry else "local",
            "unlisted": entry is None,
        })

    # Cloud models are reachable without appearing in `ollama list`, so surface any
    # the config knows about that we didn't already see.
    for name, entry in listed.items():
        if name not in installed and entry.get("where") == "cloud":
            models.append({
                "name": name,
                "roles": entry.get("roles", []),
                "where": "cloud",
                "unlisted": False,
            })

    return sorted(models, key=lambda m: m["name"])


async def for_role(role: str) -> list[str]:
    """Installed model names explicitly classified as able to do `role`.

    Unlisted models are deliberately excluded. The catalogue is a hint rather than a
    whitelist, so callers may still name one directly — but an unknown model is an
    unknown capability, and offering a text-only model as an OCR choice is worse than
    offering nothing. Use `available()` when you want everything Ollama has.
    """
    return [m["name"] for m in await available() if role in m["roles"]]
