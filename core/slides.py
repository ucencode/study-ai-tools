"""PDF slides → OCR transcript → refined document, as an async streaming pipeline.

`pdf2image` and the PNG encoding it feeds are blocking CPU work, so they run in
worker threads; only the model calls touch the event loop directly.
"""

from __future__ import annotations

import asyncio
import time
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator

from core import events as ev
from core import llm, storage
from core.languages import AUDIENCE_INSTRUCTION, LANG_INSTRUCTION
from core.prompts_slides import OCR_PROMPT, OCR_SYSTEM, REFINE_PROMPTS

OCR_MODEL_KEYWORDS = ["qwen3.5", "qwen3-vl", "qwen2.5vl", "deepseek-ocr",
                      "llama3.2-vision", "gemma4", "ministral-3", "glm-ocr"]
REFINE_MODEL_KEYWORDS = ["glm-5.1", "gemma4", "qwen3.5", "gpt-oss"]

ACTIONS = ("skip", "clean", "summary", "deep")

REFINE_TEMPERATURE = {"clean": 0, "summary": 0, "deep": 0.4}
REFINE_MAX_TOKENS = {"clean": 65536, "summary": 65536, "deep": 131072}


async def list_vision_models() -> list[str]:
    return await llm.list_models(OCR_MODEL_KEYWORDS)


async def list_refine_models() -> list[str]:
    return await llm.list_models(REFINE_MODEL_KEYWORDS)


def ocr_max_tokens(image_size_kb: float) -> int:
    if image_size_kb < 500:
        return 1024
    if image_size_kb < 1000:
        return 2048
    return 4096


# ── stage 1: OCR ──────────────────────────────────────────────────────────────

def _render_pages(path: Path, dpi: int) -> list:
    from pdf2image import convert_from_path

    return convert_from_path(str(path), dpi=dpi)


def _encode_png(page) -> bytes:
    buf = BytesIO()
    page.save(buf, format="PNG")
    return buf.getvalue()


async def _ocr_page(page, index: int, total: int, ocr_model: str) -> tuple[str, int]:
    raw = await asyncio.to_thread(_encode_png, page)
    try:
        response = await llm.client().chat(
            model=ocr_model,
            options={"temperature": 0, "num_ctx": 8192,
                     "num_predict": ocr_max_tokens(len(raw) / 1024)},
            stream=False,
            think=False,
            messages=[
                {"role": "system", "content": OCR_SYSTEM},
                llm.image_message(OCR_PROMPT, [raw]),
            ],
        )
    except Exception as e:
        # one unreadable page shouldn't sink a 60-page deck
        return f"[missing page {index}] ({e})", 0
    return response.message.content or "", response.eval_count or 0


async def ocr_pdf(path: Path, ocr_model: str, dpi: int = 200) -> AsyncIterator[ev.StreamEvent]:
    """Stream the transcript page by page.

    Ollama returns vision completions in one shot, so a page is the streaming
    unit here: each finished page is emitted as a `token` event, and the final
    `meta` event carries the assembled transcript.
    """
    yield ev.status(f"loading PDF: {path.name}", stage="ocr")
    started = time.time()

    pages = await asyncio.to_thread(_render_pages, path, dpi)
    total = len(pages)
    yield ev.status(f"{total} pages found, dpi={dpi}, model={ocr_model}",
                    stage="ocr", pages=total)

    parts: list[str] = []
    total_tokens = 0
    for i, page in enumerate(pages, 1):
        page_start = time.time()
        yield ev.status(f"page {i}/{total} → {ocr_model}...", stage="ocr",
                        page=i, pages=total)

        text, tokens = await _ocr_page(page, i, total, ocr_model)
        total_tokens += tokens
        chunk = f"--- Page {i} ---\n{text}"
        parts.append(chunk)

        yield ev.token(("\n\n" if i > 1 else "") + chunk)
        yield ev.status(
            f"page {i}/{total} done ({time.time() - page_start:.2f}s, "
            f"{len(text)} chars, {tokens} tokens)",
            stage="ocr", page=i, pages=total,
        )

    yield ev.status(f"OCR completed in {time.time() - started:.2f}s", stage="ocr")
    yield ev.meta(transcript="\n\n".join(parts), pages=total, tokens=total_tokens)


# ── stage 2: refine ───────────────────────────────────────────────────────────

async def refine(text: str, *, action: str, lang: str, model: str,
                 audience: str | None = None) -> AsyncIterator[str]:
    prompt = REFINE_PROMPTS[action] + "\n\n" + f"Respond and deliver the output in {LANG_INSTRUCTION[lang]}."
    if audience:
        prompt += "\n\n" + AUDIENCE_INSTRUCTION[audience]

    async for chunk in llm.stream_chat(
        model=model,
        options={
            "temperature": REFINE_TEMPERATURE.get(action, 0),
            "num_predict": REFINE_MAX_TOKENS.get(action, 8192),
            "num_ctx": 32768,
        },
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
    ):
        yield chunk


# ── the pipeline ──────────────────────────────────────────────────────────────

async def generate(
    *,
    pdf_path: Path,
    ocr_model: str,
    action: str = "skip",
    refine_model: str | None = None,
    lang: str = "auto",
    level: str | None = None,
    dpi: int = 200,
    use_cache: bool = True,
) -> AsyncIterator[ev.StreamEvent]:
    """OCR a PDF and optionally refine the transcript, streaming both stages."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        yield ev.error(f"file not found: {pdf_path}")
        return
    if action not in ACTIONS:
        yield ev.error(f"unknown action '{action}' — expected one of {', '.join(ACTIONS)}")
        return
    if lang not in LANG_INSTRUCTION:
        yield ev.error(f"unknown language '{lang}'")
        return
    if action != "skip" and not refine_model:
        yield ev.error(f"action '{action}' needs a refine model")
        return
    if level is not None and level not in AUDIENCE_INSTRUCTION:
        yield ev.error(f"unknown audience level '{level}'")
        return

    stamp = storage.timestamp()
    pdf_name = pdf_path.name

    try:
        raw_path = storage.find_cached_ocr(pdf_name, ocr_model) if use_cache else None
        if raw_path:
            transcript = storage.load_raw_ocr(raw_path)
            raw_file = raw_path.name
            yield ev.status(f"cache hit — reusing OCR from {raw_file} "
                            f"({len(transcript)} chars)", stage="cache")
            yield ev.section("ocr", "OCR Transcript", restored=True)
            yield ev.token(transcript)
        else:
            yield ev.section("ocr", "OCR Transcript")
            transcript = ""
            pages = 0
            async for event in ocr_pdf(pdf_path, ocr_model, dpi):
                if event.type == ev.META:
                    transcript = event.data["transcript"]
                    pages = event.data["pages"]
                    continue
                yield event
            await llm.unload(ocr_model)
            raw_path = storage.save_raw_ocr(transcript, stamp, pdf_name=pdf_name,
                                            pages=pages, dpi=dpi, model=ocr_model)
            raw_file = raw_path.name
            yield ev.status(f"raw → {raw_path}", stage="output")

        yield ev.done(path=str(raw_path), name=raw_file, tool="slide-summarizinator",
                      stage="ocr", final=action == "skip")
        if action == "skip":
            return

        audience = level if action in ("summary", "deep") else None
        yield ev.status(
            f"mode={action} lang={LANG_INSTRUCTION[lang]}"
            + (f" audience={audience}" if audience else "")
            + f" model={refine_model} — sending {len(transcript)} chars",
            stage="refine",
        )
        yield ev.section("refined", {"clean": "Cleaned Text", "summary": "Study Notes",
                                     "deep": "Structured Document"}[action])

        started = time.time()
        chunks: list[str] = []
        async for chunk in refine(transcript, action=action, lang=lang,
                                  model=refine_model, audience=audience):
            chunks.append(chunk)
            yield ev.token(chunk)
        compiled = "".join(chunks)
        yield ev.status(f"refine done ({time.time() - started:.2f}s, {len(compiled)} chars)",
                        stage="refine")

    except llm.LLMError as e:
        yield ev.error(str(e))
        return

    await llm.unload(refine_model)
    compiled_path = storage.save_refined(
        compiled, stamp, origin=pdf_name, raw_file=raw_file,
        model=refine_model, mode=action, lang=lang, level=audience,
    )
    yield ev.status(f"compiled → {compiled_path}", stage="output")
    yield ev.done(path=str(compiled_path), name=compiled_path.name,
                  tool="slide-summarizinator", stage="refine", final=True)
