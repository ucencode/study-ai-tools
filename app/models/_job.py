from typing import Any, Literal, TypedDict


class JobProgress(TypedDict):
    stage: str
    current: int
    total: int


class Job(TypedDict):
    id: str
    service: str
    status: Literal["queued", "processing", "completed", "failed"]
    created_at: str
    updated_at: str
    progress: JobProgress | None
    input_path: str
    error: str | None
    output_path: str