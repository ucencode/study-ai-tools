"""Async Ollama access.

Local and Ollama Cloud go through the same client — a cloud model is identified only
by its name (``gpt-oss:120b-cloud``). Set OLLAMA_HOST / OLLAMA_API_KEY to point at a
remote Ollama instead of the local one.
"""

import json
import os
import re
from typing import Any, AsyncIterator, Iterable, Sequence

from ollama import AsyncClient

_client: AsyncClient | None = None


class LLMError(RuntimeError):
    """Anything that went wrong talking to Ollama."""


def client() -> AsyncClient:
    global _client
    if _client is None:
        headers = {}
        if api_key := os.environ.get("OLLAMA_API_KEY"):
            headers["Authorization"] = f"Bearer {api_key}"
        _client = AsyncClient(host=os.environ.get("OLLAMA_HOST"), headers=headers)
    return _client


# Ollama names cloud models both ways, e.g. gpt-oss:120b-cloud and gemma4:cloud.
CLOUD_SUFFIXES = ("-cloud", ":cloud")


def is_cloud(model: str) -> bool:
    return model.endswith(CLOUD_SUFFIXES)


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
    """Evict a model from VRAM. Best effort — never fatal, and pointless for cloud."""
    if is_cloud(model):
        return
    try:
        await client().generate(model=model, keep_alive=0)
    except Exception:
        pass


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
            if text := chunk.message.content:
                yield text
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
    # markdown fences
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE)
    # // line comments
    raw = re.sub(r"//[^\n]*", "", raw)
    # # line comments (only when not inside a string — best-effort)
    raw = re.sub(r"(?<![\"'\w])#[^\n]*", "", raw)
    # trailing commas before ] or }
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw.strip()


def image_message(prompt: str, images: Iterable[bytes]) -> dict:
    return {"role": "user", "content": prompt, "images": list(images)}
