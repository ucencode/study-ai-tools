"""Async Ollama access.

The CLIs used the blocking ``ollama.chat`` plus ``subprocess`` calls to the
``ollama`` binary. Everything here is coroutine-based instead, so a single
uvicorn worker can stream a response without blocking the event loop.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Iterable, Sequence

from ollama import AsyncClient

_client: AsyncClient | None = None


class LLMError(RuntimeError):
    """Anything that went wrong talking to Ollama."""


def client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient()
    return _client


# ── model discovery ───────────────────────────────────────────────────────────

async def list_models(keywords: Sequence[str] | None = None) -> list[str]:
    """Installed model names, optionally filtered to those matching `keywords`."""
    try:
        response = await client().list()
    except Exception as e:  # connection refused, bad host, ...
        raise LLMError(f"could not reach Ollama — is it running? ({e})") from e

    names = sorted({m.model for m in response.models if m.model})
    if keywords is None:
        return names
    return [name for name in names if any(kw in name for kw in keywords)]


async def unload(model: str) -> None:
    """Evict a model from VRAM. Best effort — never fatal."""
    try:
        await client().generate(model=model, keep_alive=0)
    except Exception:
        pass


# ── generation ────────────────────────────────────────────────────────────────

async def stream_chat(
    *,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    think: bool | None = None,
) -> AsyncIterator[str]:
    """Yield content chunks as the model emits them."""
    kwargs: dict[str, Any] = {}
    if think is not None:
        kwargs["think"] = think

    try:
        stream = await client().chat(
            model=model,
            messages=messages,
            options=options or {},
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            text = chunk.message.content
            if text:
                yield text
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"generation failed on '{model}': {e}") from e


async def complete(
    *,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    think: bool | None = None,
) -> str:
    """Single non-streaming completion."""
    kwargs: dict[str, Any] = {}
    if think is not None:
        kwargs["think"] = think

    try:
        response = await client().chat(
            model=model,
            messages=messages,
            options=options or {},
            stream=False,
            **kwargs,
        )
    except Exception as e:
        raise LLMError(f"generation failed on '{model}': {e}") from e
    return response.message.content or ""


async def complete_json(
    *,
    model: str,
    messages: list[dict],
    options: dict | None = None,
) -> Any:
    """Completion parsed as JSON, with the usual model artifacts stripped first."""
    raw = await complete(model=model, messages=messages, options=options)
    cleaned = sanitize_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"expected JSON from '{model}' but parsing failed: {e}\n\n{cleaned}") from e


def sanitize_json(raw: str) -> str:
    """Strip common model artifacts that break json.loads."""
    # strip markdown fences
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE)
    # strip // line comments
    raw = re.sub(r"//[^\n]*", "", raw)
    # strip # line comments (only when not inside a string — best-effort)
    raw = re.sub(r"(?<![\"'\w])#[^\n]*", "", raw)
    # strip trailing commas before ] or }
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw.strip()


def image_message(prompt: str, images: Iterable[bytes]) -> dict:
    return {"role": "user", "content": prompt, "images": list(images)}
