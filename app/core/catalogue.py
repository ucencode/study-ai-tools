"""Which models can play which role, from config/models.toml.

The catalogue is a hint, not a whitelist. Anything Ollama has installed is usable;
listing it here only tells the UI what to offer for each role.
"""

import tomllib

from app.core import llm
from app.core.paths import MODELS_FILE

ROLES = ("vision", "refine", "llm")


def _entries() -> list[dict]:
    if not MODELS_FILE.exists():
        return []
    with MODELS_FILE.open("rb") as file:
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
    """Installed model names that can do `role`, plus every unlisted one."""
    return [
        m["name"] for m in await available()
        if role in m["roles"] or m["unlisted"]
    ]
