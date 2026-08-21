from typing import Literal

from pydantic import Field

from app.models._job import Job, Strict

SourceFormat = Literal["pdf", "pptx"]
RefineAction = Literal["skip", "clean", "summary", "deep"]
AudienceLevel = Literal["beginner", "intermediate", "advanced"]

SERVICE = "slide_summarizer"


class SlideSummarizerParams(Strict):
    filename: str
    source_format: SourceFormat
    dpi: int = Field(default=200, ge=50, le=600)
    ocr_model: str
    action: RefineAction = "skip"
    refine_model: str | None = None
    lang: str = "auto"
    level: AudienceLevel | None = None


class SlideSummarizerResult(Strict):
    pages: int
    raw_chars: int
    output_chars: int = 0
    ocr_cached: bool = False


class SlideSummarizerJob(Job):
    service: str = SERVICE
    params: SlideSummarizerParams
    result: SlideSummarizerResult | None = None
