from typing import TypedDict

from ._job import Job


class SlideSummarizerData(TypedDict):
    origin: str
    file: str
    timestamp: str
    model: str
    mode: Literal["clean", "summary", "deep", "skip"]
    lang: str
    level: int


class SlideSummarizerJob(Job):
    data: SlideSummarizerData