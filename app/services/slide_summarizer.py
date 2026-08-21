"""Slides → OCR → refined document.

Every stage writes into the job directory as it goes, so a client polling the job
sees real progress and a crashed run leaves whatever it finished behind.
"""

import asyncio
import hashlib
import shutil
from pathlib import Path

from app.core import documents, llm
from app.core.languages import AUDIENCE_INSTRUCTION, LANG_INSTRUCTION
from app.core.prompts import slide_summarizer as prompts
from app.models._job import now
from app.models.slide_summarizer import (
    SlideSummarizerJob,
    SlideSummarizerParams,
    SlideSummarizerResult,
)
from app.repositories._job import new_id
from app.repositories.slide_summarizer import SlideSummarizerRepository

RAW_FILE = "raw.txt"
OUTPUT_FILE = "output.md"


class SlideSummarizerService:
    def __init__(self, repository: SlideSummarizerRepository | None = None):
        self.repository = repository or SlideSummarizerRepository()

    # ── queries ──────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> SlideSummarizerJob | None:
        return self.repository.select_by_id(job_id)

    def select_all(self) -> list[SlideSummarizerJob]:
        return self.repository.select_all()

    def delete(self, job_id: str) -> None:
        self.repository.delete(job_id)

    def output(self, job_id: str) -> str:
        """Whatever the job has produced so far — partial while it is still running."""
        job = self.repository.select_by_id(job_id)
        if job is None:
            raise FileNotFoundError(f"no such job: {job_id}")

        for name in (OUTPUT_FILE, RAW_FILE):
            path = self.repository.resolve(job_id, name)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    # ── creation ─────────────────────────────────────────────────────────────

    def create(self, params: SlideSummarizerParams, source: Path | bytes) -> SlideSummarizerJob:
        """Register a queued job and store its input file.

        `source` is a path when the CLI calls us and raw bytes when an upload does.
        """
        if params.source_format == "pptx" and not documents.libreoffice_available():
            raise documents.DocumentError(
                "LibreOffice is not installed, so .pptx input cannot be converted. "
                "Install it, or export the deck to PDF yourself."
            )
        if params.action != "skip" and not params.refine_model:
            raise ValueError(f"action '{params.action}' needs a refine_model")

        job_id = new_id()
        job_dir = self.repository.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        input_name = f"input.{params.source_format}"
        target = job_dir / input_name
        if isinstance(source, bytes):
            target.write_bytes(source)
        else:
            shutil.copyfile(source, target)

        params = params.model_copy(update={"source_sha256": _sha256(target)})

        return self.repository.create(
            SlideSummarizerJob(id=job_id, input_path=input_name, params=params)
        )

    # ── the pipeline ─────────────────────────────────────────────────────────

    async def run(self, job_id: str) -> SlideSummarizerJob:
        job = self.repository.select_by_id(job_id)
        if job is None:
            raise FileNotFoundError(f"no such job: {job_id}")

        self.repository.set_status(job_id, "processing")
        params = job.params

        try:
            pdf = await self._as_pdf(job_id, job.input_path, params.source_format)
            raw_text, pages, cached = await self._transcribe(job_id, pdf, params)

            result = SlideSummarizerResult(
                pages=pages, raw_chars=len(raw_text), ocr_cached=cached
            )
            output_name = RAW_FILE

            if params.action != "skip":
                refined = await self._refine(job_id, raw_text, params)
                result.output_chars = len(refined)
                output_name = OUTPUT_FILE

            job = self.repository.require(job_id)
            job.result = result
            job.output_path = output_name
            job.status = "completed"
            job.error = None
            job.finished_at = now()
            job.progress = None
            return self.repository.update(job)

        except Exception as e:
            return self.repository.set_status(job_id, "failed", f"{type(e).__name__}: {e}")
        finally:
            await llm.unload(params.ocr_model)
            if params.refine_model:
                await llm.unload(params.refine_model)

    async def _as_pdf(self, job_id: str, input_path: str, source_format: str) -> Path:
        source = self.repository.resolve(job_id, input_path)
        if source_format == "pdf":
            return source

        self.repository.set_progress(job_id, "convert", 0, 1)
        # LibreOffice is allowed 300 seconds. Running it inline would freeze the event
        # loop this worker shares with the API, so polling a job would stall behind it.
        converted = await asyncio.to_thread(
            documents.pptx_to_pdf, source, self.repository.job_dir(job_id)
        )
        # LibreOffice names it after the input stem; normalize so the job dir is predictable.
        target = self.repository.job_dir(job_id) / "converted.pdf"
        if converted != target:
            converted.replace(target)
        self.repository.set_progress(job_id, "convert", 1, 1)
        return target

    async def _transcribe(
        self, job_id: str, pdf: Path, params: SlideSummarizerParams
    ) -> tuple[str, int, bool]:
        """OCR every page, or reuse an earlier job's transcript for the same input."""
        raw_path = self.repository.resolve(job_id, RAW_FILE)

        if cached := self._cached_raw(job_id, params):
            shutil.copyfile(cached, raw_path)
            text = raw_path.read_text(encoding="utf-8")
            return text, text.count("--- Page "), True

        total = await asyncio.to_thread(documents.page_count, pdf)
        pages: list[str] = []

        with raw_path.open("w", encoding="utf-8") as out:
            for index in range(total):
                self.repository.set_progress(job_id, "ocr", index, total)
                image = await asyncio.to_thread(
                    documents.render_page, pdf, index, params.dpi
                )
                text = await self._ocr_page(image, params.ocr_model, index)
                page = f"--- Page {index + 1} ---\n{text}"
                pages.append(page)
                out.write(page + "\n\n")
                out.flush()

        self.repository.set_progress(job_id, "ocr", total, total)
        return "\n\n".join(pages), total, False

    async def _ocr_page(self, image: bytes, model: str, index: int) -> str:
        """One page. A failure here is a hole in the document, not a dead job."""
        try:
            return await llm.complete(
                model=model,
                think=False,
                options={
                    "temperature": 0,
                    "num_ctx": 8192,
                    "num_predict": prompts.ocr_max_tokens(len(image) / 1024),
                },
                messages=[
                    {"role": "system", "content": prompts.OCR_SYSTEM},
                    llm.image_message(prompts.OCR_PROMPT, [image]),
                ],
            )
        except llm.LLMError:
            return f"[missing page {index + 1}]"

    def _cached_raw(self, job_id: str, params: SlideSummarizerParams) -> Path | None:
        """A completed job that already OCR'd this exact file with this same model.

        Keyed on the content digest: matching on the filename would hand Tuesday's
        "lecture.pdf" the transcript of Monday's.
        """
        if not params.source_sha256:
            return None
        for job in self.repository.select_all():
            if job.id == job_id or job.status != "completed":
                continue
            if job.params.source_sha256 != params.source_sha256:
                continue
            if job.params.ocr_model != params.ocr_model or job.params.dpi != params.dpi:
                continue
            path = self.repository.job_dir(job.id) / RAW_FILE
            if path.exists():
                return path
        return None

    async def _refine(self, job_id: str, text: str, params: SlideSummarizerParams) -> str:
        self.repository.set_progress(job_id, "refine", 0, 1)

        system = prompts.REFINE_PROMPTS[params.action]
        system += f"\n\nRespond and deliver the output in {LANG_INSTRUCTION[params.lang]}."
        if params.level and params.action in ("summary", "deep"):
            system += "\n\n" + AUDIENCE_INSTRUCTION[params.level]

        output_path = self.repository.resolve(job_id, OUTPUT_FILE)
        chunks: list[str] = []

        with output_path.open("w", encoding="utf-8") as out:
            stream = llm.stream_chat(
                model=params.refine_model,
                options={
                    "temperature": prompts.REFINE_TEMPERATURE.get(params.action, 0),
                    "num_predict": prompts.REFINE_MAX_TOKENS.get(params.action, 8192),
                    "num_ctx": 32768,
                },
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
            )
            async for chunk in stream:
                chunks.append(chunk)
                out.write(chunk)
                out.flush()

        self.repository.set_progress(job_id, "refine", 1, 1)
        return "".join(chunks)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
