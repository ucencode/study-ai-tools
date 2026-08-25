from typing import Literal

from pydantic import Field

from app.models._job import Job, Strict

SourceFormat = Literal["pdf", "pptx"]
RefineAction = Literal["skip", "clean", "summary", "deep"]
AudienceLevel = Literal["beginner", "intermediate", "advanced"]

SERVICE = "slide_summarizer"


class SlideSummarizerSettings(Strict):
    """The part of a run a preset can fix: everything except the deck itself.

    Params is this plus the source, so a new option is presettable by default.
    """

    dpi: int = Field(default=200, ge=50, le=600)
    ocr_model: str
    action: RefineAction = "skip"
    refine_model: str | None = None
    lang: str = "auto"
    level: AudienceLevel | None = None


class SlideSummarizerParams(SlideSummarizerSettings):
    filename: str
    # What the OCR cache keys on. Two people both uploading "lecture.pdf" are not
    # uploading the same lecture, so the name cannot establish identity.
    source_sha256: str = ""
    source_format: SourceFormat


class SlideSummarizerResult(Strict):
    pages: int
    raw_chars: int
    output_chars: int = 0
    ocr_cached: bool = False


class SlideSummarizerJob(Job):
    service: str = SERVICE
    params: SlideSummarizerParams
    result: SlideSummarizerResult | None = None
