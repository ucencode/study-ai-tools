"""The persistence rules the pipelines lean on."""

import logging

import pytest

from app.core import paths
from app.models.curriculum_generator import (
    ChapterState,
    CurriculumGeneratorJob,
    CurriculumGeneratorParams,
)
from app.repositories.curriculum_generator import CurriculumGeneratorRepository


@pytest.fixture
def repository():
    return CurriculumGeneratorRepository()


def make(repository, job_id="20260101000000-aaaa", **fields):
    job = CurriculumGeneratorJob(
        id=job_id,
        input_path="input.txt",
        params=CurriculumGeneratorParams(source_name="syllabus.txt", model="gpt-oss:20b"),
        **fields,
    )
    repository.job_dir(job_id).mkdir(parents=True, exist_ok=True)
    return repository.create(job)


def test_resolve_refuses_to_leave_the_job_directory(repository):
    make(repository)

    assert repository.resolve("20260101000000-aaaa", "plan.md").name == "plan.md"
    with pytest.raises(FileNotFoundError):
        repository.resolve("20260101000000-aaaa", "../../../etc/passwd")


def test_job_json_is_the_resume_authority_not_the_files_on_disk(repository):
    """A stray chapter file from a crash must not look like finished work."""
    job = make(repository, chapters=[ChapterState(topic="One", file="chapters/01.md")])
    (repository.job_dir(job.id) / "chapters").mkdir(parents=True, exist_ok=True)
    (repository.job_dir(job.id) / "chapters" / "02.md").write_text("half a chapter")

    reloaded = repository.select_by_id(job.id)

    assert [chapter.file for chapter in reloaded.chapters] == ["chapters/01.md"]


def test_a_record_that_no_longer_fits_the_schema_is_skipped_not_fatal(repository, caplog):
    good = make(repository, job_id="20260101000000-good")
    broken = repository.job_dir("20260101000000-bad")
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "job.json").write_text('{"id": "x", "service": "curriculum_generator"}')

    with caplog.at_level(logging.WARNING):
        jobs = repository.select_all()

    assert [job.id for job in jobs] == [good.id]
    assert "skipping unreadable job record" in caplog.text


def test_ending_a_job_clears_its_progress_and_stamps_the_finish(repository):
    job = make(repository)
    repository.set_progress(job.id, "chapters", 1, 4)
    assert repository.select_by_id(job.id).progress.current == 1

    finished = repository.set_status(job.id, "completed")

    assert finished.progress is None
    assert finished.finished_at is not None


def test_requeueing_clears_the_previous_attempts_finish_and_error(repository):
    job = make(repository)
    repository.set_status(job.id, "failed", "LLMError: boom")

    requeued = repository.set_status(job.id, "queued")

    assert requeued.error is None
    assert requeued.finished_at is None


def test_delete_takes_the_whole_job_directory(repository):
    job = make(repository)
    (repository.job_dir(job.id) / "plan.md").write_text("plan")

    repository.delete(job.id)

    assert not repository.job_dir(job.id).exists()
    assert repository.select_by_id(job.id) is None


def test_records_are_written_atomically(repository):
    """A half-written job.json would be a record that cannot be read back."""
    job = make(repository)
    repository.set_progress(job.id, "plan", 0, 1)

    assert list(repository.job_dir(job.id).glob("*.tmp")) == []
    assert (repository.job_dir(job.id) / "job.json").exists()


def test_the_jobs_directory_is_the_one_under_data(repository):
    assert repository.directory == paths.JOBS_DIR / "curriculum_generator"
