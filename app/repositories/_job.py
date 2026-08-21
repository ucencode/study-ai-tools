import logging
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import ValidationError

from app.core.paths import JOBS_DIR
from app.models._job import Job, JobProgress, JobStatus, now

logger = logging.getLogger(__name__)

JobT = TypeVar("JobT", bound=Job)


def new_id() -> str:
    """Sortable and collision-free enough for a single-user tool."""
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"


class JobRepository(Generic[JobT]):
    """One directory per job: job.json plus every file that run produced.

    Keeping artifacts beside the record is what makes delete a single rmtree and
    resume a matter of looking at what is already on disk.
    """

    service: str
    model: type[JobT]

    def __init__(self, service: str, model: type[JobT]):
        self.service = service
        self.model = model
        self.directory = JOBS_DIR / service
        self.directory.mkdir(parents=True, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────────

    def job_dir(self, id: str) -> Path:
        return self.directory / id

    def _record_path(self, id: str) -> Path:
        return self.job_dir(id) / "job.json"

    def resolve(self, id: str, name: str) -> Path:
        """A file inside a job directory, refusing anything that escapes it."""
        root = self.job_dir(id).resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise FileNotFoundError(f"{name} is outside job {id}")
        return path

    # ── read ─────────────────────────────────────────────────────────────────

    def select_all(self) -> list[JobT]:
        jobs = []
        for path in self.directory.glob("*/job.json"):
            try:
                jobs.append(self.model.model_validate_json(path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                continue  # deleted between the glob and the read
            except ValidationError as e:
                # A record that no longer matches the schema is skipped so one bad job
                # cannot break the listing — but silence would make it simply vanish.
                logger.warning("skipping unreadable job record %s: %s", path, e)
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def select_by_id(self, id: str) -> JobT | None:
        path = self._record_path(id)
        if not path.exists():
            return None
        return self.model.model_validate_json(path.read_text(encoding="utf-8"))

    # ── write ────────────────────────────────────────────────────────────────

    def create(self, job: JobT) -> JobT:
        path = self._record_path(job.id)
        if path.exists():
            raise FileExistsError(f"Job {job.id} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write(job)
        return job

    def update(self, job: JobT) -> JobT:
        if not self._record_path(job.id).exists():
            raise FileNotFoundError(f"Job {job.id} does not exist")
        job.updated_at = now()
        self._write(job)
        return job

    def delete(self, id: str) -> None:
        shutil.rmtree(self.job_dir(id), ignore_errors=True)

    # ── the two updates every pipeline makes ─────────────────────────────────

    def set_status(self, id: str, status: JobStatus, error: str | None = None) -> JobT:
        job = self.require(id)
        job.status = status
        # A retry starts clean — a stale error on a completed job reads as a failure.
        job.error = error
        # started_at/finished_at describe the *current* attempt, so a retry clears the
        # previous one's — a job that is processing must not carry a finish time.
        if status == "queued":
            job.finished_at = None
        if status == "processing":
            job.started_at = now()
            job.finished_at = None
        if status in ("completed", "failed"):
            job.finished_at = now()
            job.progress = None
        return self.update(job)

    def set_progress(self, id: str, stage: str, current: int, total: int) -> JobT:
        job = self.require(id)
        job.progress = JobProgress(stage=stage, current=current, total=total)
        return self.update(job)

    def require(self, id: str) -> JobT:
        job = self.select_by_id(id)
        if job is None:
            raise FileNotFoundError(f"Job {id} does not exist")
        return job

    def _write(self, job: JobT) -> None:
        path = self._record_path(job.id)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            job.model_dump_json(indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)
