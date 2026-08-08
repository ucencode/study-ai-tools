"""Background jobs: pipelines that outlive the request that started them.

A generation used to *be* an HTTP request — closing the tab cancelled the
generator mid-run. Here a submission returns an id immediately, a single worker
task executes jobs FIFO (one local Ollama, one GPU), and clients attach to a
job's event stream as spectators. Detaching, reloading or reattaching never
touches the run.

Every event is appended to ``outputs/.jobs/<id>.jsonl`` as it is produced, so
attaching replays the whole output from the start: a refreshed tab renders the
complete document rather than only what arrives after reconnecting.

The registry lives in this process, so the server must run a single worker.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime
from typing import AsyncIterator, Callable, Iterator

from core import events as ev
from core.paths import JOBS_DIR

# job.status
QUEUED      = "queued"
RUNNING     = "running"
DONE        = "done"
ERROR       = "error"
CANCELLED   = "cancelled"
INTERRUPTED = "interrupted"  # the server died while it was queued or running

TERMINAL = frozenset({DONE, ERROR, CANCELLED, INTERRUPTED})

KEEP_TERMINAL = 50  # older finished jobs are pruned on startup

PipelineFactory = Callable[[dict], AsyncIterator[ev.StreamEvent]]

_factories: dict[str, PipelineFactory] = {}
_records: dict[str, dict] = {}
_subscribers: dict[str, set[asyncio.Queue]] = {}
_queue: asyncio.Queue[str] | None = None
_current: tuple[str, asyncio.Task] | None = None  # the job being executed
_worker_task: asyncio.Task | None = None


# ── registry ──────────────────────────────────────────────────────────────────

def register(tool: str, factory: PipelineFactory) -> None:
    """Bind a tool name to the callable that turns stored params into a pipeline.

    Keeps this module free of any pipeline import — the app wires both tools up
    at startup instead.
    """
    _factories[tool] = factory


# ── record persistence ────────────────────────────────────────────────────────

def _record_path(job_id: str):
    return JOBS_DIR / f"{job_id}.json"


def _log_path(job_id: str):
    return JOBS_DIR / f"{job_id}.jsonl"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write(record: dict) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _record_path(record["id"]).write_text(json.dumps(record, indent=2), encoding="utf-8")


def _load_all() -> None:
    """Rebuild the in-memory index from disk. Called once, at startup."""
    _records.clear()
    if not JOBS_DIR.exists():
        return
    for path in JOBS_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue  # half-written record from a hard kill
        if isinstance(record, dict) and record.get("id"):
            _records[record["id"]] = record


def _logged_count(job_id: str) -> int:
    """How many events actually reached the log.

    A record's own `event_count` is only flushed on a status change, so a job the
    server died under under-reports it — and since the replay cursor comes from
    that number, its output would be unreachable. The log is the truth.
    """
    path = _log_path(job_id)
    if not path.exists():
        return 0
    last = -1
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("i", last)
            except json.JSONDecodeError:
                break  # torn tail from a hard kill
    return last + 1


def _read_log(job_id: str, start: int, stop: int) -> Iterator[ev.StreamEvent]:
    """Replay logged events with index in [start, stop)."""
    path = _log_path(job_id)
    if not path.exists() or stop <= start:
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn final line
            index = entry.get("i", -1)
            if index < start:
                continue
            if index >= stop:
                break
            yield ev.StreamEvent(entry["type"], entry.get("data", {}))


# ── submission ────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"


def submit(tool: str, params: dict, label: str = "") -> dict:
    """Queue a job and return its record. Never blocks on the pipeline."""
    if tool not in _factories:
        raise KeyError(f"no pipeline registered for tool '{tool}'")
    if _queue is None:
        raise RuntimeError("job worker is not running")

    record = {
        "id": _new_id(),
        "tool": tool,
        "label": label,
        "status": QUEUED,
        "params": params,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "event_count": 0,
        "progress": None,
        "results": [],
        "error": None,
    }
    _records[record["id"]] = record
    _write(record)
    _queue.put_nowait(record["id"])
    return record


def get(job_id: str) -> dict | None:
    return _records.get(job_id)


def listing(tool: str | None = None) -> list[dict]:
    """Every known job, newest first."""
    records = [r for r in _records.values() if tool is None or r["tool"] == tool]
    return sorted(records, key=lambda r: r["created_at"], reverse=True)


def delete(job_id: str) -> None:
    """Forget a finished job and its event log."""
    record = _records.get(job_id)
    if record is None:
        raise KeyError(job_id)
    if record["status"] not in TERMINAL:
        raise ValueError(f"job {job_id} is {record['status']} — cancel it first")
    _records.pop(job_id, None)
    _record_path(job_id).unlink(missing_ok=True)
    _log_path(job_id).unlink(missing_ok=True)


def cancel(job_id: str) -> dict:
    """Stop a running job, or drop a queued one before it ever starts."""
    record = _records.get(job_id)
    if record is None:
        raise KeyError(job_id)
    if record["status"] in TERMINAL:
        return record

    if _current is not None and _current[0] == job_id:
        _current[1].cancel()  # the worker records the terminal state
        return record

    # still queued — the worker skips any job that is no longer QUEUED
    _finish(record, CANCELLED)
    return record


# ── fan-out ───────────────────────────────────────────────────────────────────

def _publish(job_id: str, index: int, event: ev.StreamEvent) -> None:
    for queue in _subscribers.get(job_id, ()):
        queue.put_nowait((index, event))


def _finish(record: dict, status: str, error: str | None = None) -> None:
    record["status"] = status
    record["finished_at"] = _now()
    if error is not None:
        record["error"] = error
    _write(record)
    # -1 keeps the terminal frame ahead of no replay cursor
    _publish(record["id"], -1, ev.job(record))


# ── the worker ────────────────────────────────────────────────────────────────

async def worker() -> None:
    """Execute queued jobs one at a time, forever. Spawned once at startup.

    Each job gets its own child task, so cancelling a job leaves the worker
    itself untouched — `asyncio.wait` reports the child's fate instead of
    re-raising it here.
    """
    global _current
    assert _queue is not None
    while True:
        job_id = await _queue.get()
        record = _records.get(job_id)
        if record is None or record["status"] != QUEUED:
            continue  # cancelled or deleted while it waited its turn

        task = asyncio.create_task(_run(record), name=f"job:{job_id}")
        _current = (job_id, task)
        try:
            await asyncio.wait({task})
        finally:
            _current = None

        if record["status"] in TERMINAL:
            continue  # _run (or shutdown) already recorded the outcome
        if task.cancelled():
            _finish(record, CANCELLED)
        elif (exc := task.exception()) is not None:
            _finish(record, ERROR, f"{type(exc).__name__}: {exc}")


async def _run(record: dict) -> None:
    """Drive one pipeline, logging and broadcasting every event it yields."""
    job_id = record["id"]
    record["status"] = RUNNING
    record["started_at"] = _now()
    _write(record)
    _publish(job_id, -1, ev.job(record))

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    pipeline = _factories[record["tool"]](record["params"])

    failed: str | None = None
    with _log_path(job_id).open("a", encoding="utf-8") as log:
        try:
            async for event in pipeline:
                index = record["event_count"]
                log.write(json.dumps({"i": index, "type": event.type, "data": event.data},
                                     ensure_ascii=False) + "\n")
                record["event_count"] = index + 1

                if event.type != ev.TOKEN:
                    log.flush()  # a lost token tail is survivable; a lost status isn't
                    _absorb(record, event)
                    if event.type == ev.ERROR:
                        failed = event.data.get("message", "pipeline failed")

                _publish(job_id, index, event)
        finally:
            log.flush()
            try:
                await pipeline.aclose()  # let the pipeline unwind its own state
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    _finish(record, ERROR if failed else DONE, failed)


def _absorb(record: dict, event: ev.StreamEvent) -> None:
    """Mirror the parts of an event the job list needs to render without replay."""
    if event.type == ev.DONE:
        record["results"].append(event.data)
    elif event.type == ev.STATUS:
        data = event.data
        for done_key, total_key in (("completed", "total"), ("page", "pages")):
            if isinstance(data.get(done_key), int) and isinstance(data.get(total_key), int):
                record["progress"] = {"completed": data[done_key], "total": data[total_key]}
                break


# ── attaching ─────────────────────────────────────────────────────────────────

async def stream(job_id: str, from_index: int = 0) -> AsyncIterator[ev.StreamEvent]:
    """Replay a job's events from `from_index`, then follow it live until it ends.

    Subscribing happens *before* the replay cursor is read, so an event produced
    mid-replay lands in the queue rather than being missed; the index carried by
    every event then drops whatever the replay already covered.
    """
    record = _records.get(job_id)
    if record is None:
        yield ev.error(f"no such job: {job_id}")
        return

    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(job_id, set()).add(queue)
    cursor = record["event_count"]  # no await between subscribe and snapshot
    terminal = record["status"] in TERMINAL

    try:
        yield ev.job(record)
        for event in _read_log(job_id, from_index, cursor):
            yield event
        if terminal:
            return

        while True:
            index, event = await queue.get()
            if index >= 0 and index < cursor:
                continue  # already replayed
            yield event
            if event.type == ev.JOB and event.data.get("status") in TERMINAL:
                return
    finally:
        watchers = _subscribers.get(job_id)
        if watchers is not None:
            watchers.discard(queue)
            if not watchers:
                _subscribers.pop(job_id, None)


# ── lifecycle ─────────────────────────────────────────────────────────────────

async def startup() -> None:
    """Load records, flag anything the last process left mid-flight, start the worker."""
    global _queue, _worker_task
    _queue = asyncio.Queue()
    _subscribers.clear()
    _load_all()

    for record in _records.values():
        if record["status"] in (QUEUED, RUNNING):
            record["status"] = INTERRUPTED
            record["finished_at"] = _now()
            record["error"] = "the server stopped while this job was in flight"
            # whatever it wrote before dying is still readable — count it so the
            # replay cursor covers it
            record["event_count"] = _logged_count(record["id"])
            _write(record)

    _prune()
    _worker_task = asyncio.create_task(worker(), name="job-worker")


def _prune() -> None:
    finished = [r for r in listing() if r["status"] in TERMINAL]
    for record in finished[KEEP_TERMINAL:]:
        try:
            delete(record["id"])
        except (KeyError, ValueError, OSError):
            pass


async def shutdown() -> None:
    """Stop the worker and flag whatever it was running as interrupted."""
    global _queue, _worker_task

    if _current is not None:
        job_id, task = _current
        record = _records.get(job_id)
        if record is not None and record["status"] not in TERMINAL:
            _finish(record, INTERRUPTED, "the server stopped while this job was running")
        task.cancel()

    for record in _records.values():
        if record["status"] == QUEUED:
            _finish(record, INTERRUPTED, "the server stopped before this job started")

    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None

    _queue = None


__all__ = ["register", "submit", "get", "listing", "cancel", "delete", "stream",
           "worker", "startup", "shutdown", "TERMINAL", "QUEUED", "RUNNING",
           "DONE", "ERROR", "CANCELLED", "INTERRUPTED"]
