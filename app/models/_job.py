from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "processing", "completed", "failed"]

TERMINAL: frozenset[str] = frozenset({"completed", "failed"})


class Strict(BaseModel):
    """Base for every stored shape: unknown keys are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid")


class JobProgress(Strict):
    stage: str
    current: int
    total: int


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Job(Strict):
    id: str
    service: str
    status: JobStatus = "queued"
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    progress: JobProgress | None = None
    error: str | None = None

    # Both are relative to the job directory, so the record survives data/ moving.
    input_path: str
    output_path: str | None = None
