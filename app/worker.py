"""One queue, one worker, FIFO.

There is one local Ollama and one GPU, so running jobs concurrently would only make
them all slower. The queue lives in this process — run a single uvicorn worker.
"""

import asyncio

from app.services.curriculum_generator import CurriculumGeneratorService
from app.services.slide_summarizer import SlideSummarizerService

SERVICES = {
    "slide_summarizer": SlideSummarizerService,
    "curriculum_generator": CurriculumGeneratorService,
}

_queue: asyncio.Queue[tuple[str, str]] | None = None
_task: asyncio.Task | None = None
_current: tuple[str, str] | None = None


def service(name: str):
    if name not in SERVICES:
        raise KeyError(f"unknown service: {name}")
    return SERVICES[name]()


def enqueue(service_name: str, job_id: str) -> None:
    if _queue is None:
        raise RuntimeError("job worker is not running")
    _queue.put_nowait((service_name, job_id))


async def worker() -> None:
    global _current
    assert _queue is not None
    while True:
        service_name, job_id = await _queue.get()
        _current = (service_name, job_id)
        try:
            await service(service_name).run(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # run() records its own failures; anything reaching here is a bug in the
            # plumbing, and the queue outliving it matters more than the traceback.
            pass
        finally:
            _current = None


async def startup() -> None:
    global _queue, _task
    _queue = asyncio.Queue()
    _fail_orphans("the server stopped while this job was in flight")
    _task = asyncio.create_task(worker(), name="job-worker")


async def shutdown() -> None:
    global _queue, _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    _queue = None
    _fail_orphans("the server stopped while this job was in flight")


def _fail_orphans(message: str) -> None:
    """Nothing is running, so anything still marked live is a leftover."""
    for name in SERVICES:
        instance = service(name)
        for job in instance.select_all():
            if job.status in ("queued", "processing"):
                instance.repository.set_status(job.id, "failed", message)
