"""Fixtures shared by every test.

Two things happen at import time rather than in a fixture, because they have to be
true *before* the app is imported: the data directory is redirected into a temporary
one, and it has to be redirected first, since the routers instantiate their services
at import and a `JobRepository` binds its directory in `__init__`.

Ollama is never mocked at the transport level. `FakeLLM` replaces the five functions
in `app.core.llm`; services call them by module reference, so patching the attributes
works regardless of import order.
"""

import re
import shutil
import tempfile
import time
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from app.core import paths

_ROOT = Path(tempfile.mkdtemp(prefix="study-ai-tests-"))
paths.DATA_DIR = _ROOT
paths.JOBS_DIR = _ROOT / "jobs"
paths.PRESETS_DIR = _ROOT / "presets"
paths.TMP_DIR = _ROOT / "tmp"

from app.core import llm  # noqa: E402
from app.core.prompts import curriculum_generator as curriculum_prompts  # noqa: E402

TOPICS = [
    "Relational databases",
    "Transactions",
    "Locking and concurrency",
    "Isolation levels",
]

OUTLINE = [
    {"topic": TOPICS[0], "scope": "Tables, keys, joins.", "depends_on": []},
    {"topic": TOPICS[1], "scope": "ACID and the transaction boundary.", "depends_on": [TOPICS[0]]},
    {"topic": TOPICS[2], "scope": "Two-phase locking.", "depends_on": [TOPICS[1]]},
    {"topic": TOPICS[3], "scope": "Anomalies per level.", "depends_on": [TOPICS[1], TOPICS[2]]},
]

METADATA = {
    "title": "Database Systems",
    "course": "Database Systems",
    "course_code": "CS4400",
    "credits": 3,
    "topics": TOPICS,
    "outcomes": ["Model data", "Reason about concurrency"],
    "topics_count": len(TOPICS),
    "outcomes_count": 2,
    "estimated_weeks": 8,
    "tags": ["databases"],
}

QUIZ = [
    {"id": 1, "topic": TOPICS[0], "question": "Comfortable with joins?"},
    {"id": 2, "topic": TOPICS[1], "question": "Used transactions?"},
]

CHAPTER_HEADING = re.compile(r'Write chapter (\d+) of (\d+): "([^"]+)"')

PLAN_TEXT = "## Week 1\n\nRelational model, keys and joins.\n\n## Week 2\n\nTransactions.\n"
MATERIAL_TEXT = "# Material\n\nEverything, condensed.\n"
REFERENCES_TEXT = "# Further reading\n\n- A book\n"
CHAPTER_TEXT = "## Chapter body\n\nProse about the topic.\n"


class FakeLLM:
    """A scripted Ollama. Every call is recorded so tests can assert on prompts."""

    def __init__(self):
        self.calls = []            # (kind, model, system, user)
        self.chapters = []         # (index, total, topic) per chapter call, in order
        self.chapter_prompts = []  # the full user message of each chapter call
        self.ocr_pages = 0         # how many page images were transcribed

        self.installed = ["gemma3:270m", "gpt-oss:20b", "qwen2.5vl:7b"]
        self.list_error = None     # set to a message to make Ollama look unreachable
        self.fail_pages = set()    # 1-based page numbers whose OCR raises
        self.fail_chapters = set() # 1-based chapter numbers that raise, once each
        self.metadata = dict(METADATA)
        self.outline = [dict(entry) for entry in OUTLINE]
        self.quiz = [dict(question) for question in QUIZ]

    # ── the five functions the services use ──────────────────────────────────

    async def list_models(self, keywords=None):
        if self.list_error:
            raise llm.LLMError(self.list_error)
        if keywords is None:
            return sorted(self.installed)
        return [name for name in sorted(self.installed) if any(k in name for k in keywords)]

    async def unload(self, model):
        return None

    async def complete(self, *, model, messages, options=None, think=None):
        """Only OCR uses this: one call per page image."""
        self.calls.append(("complete", model, _system(messages), _user(messages)))
        self.ocr_pages += 1
        if self.ocr_pages in self.fail_pages:
            raise llm.LLMError("could not reach Ollama")
        return f"Page {self.ocr_pages} transcript."

    async def complete_json(self, *, model, messages, options=None):
        system = _system(messages)
        self.calls.append(("complete_json", model, system, _user(messages)))
        if system.startswith(curriculum_prompts.META_SYSTEM[:40]):
            return dict(self.metadata)
        if system.startswith(curriculum_prompts.ASSESS_SYSTEM[:40]):
            return [dict(question) for question in self.quiz]
        if system.startswith(curriculum_prompts.OUTLINE_SYSTEM[:40]):
            return [dict(entry) for entry in self.outline]
        raise AssertionError(f"unscripted complete_json: {system[:60]!r}")

    async def stream_chat(self, *, model, messages, options=None, think=None):
        system, user = _system(messages), _user(messages)
        self.calls.append(("stream_chat", model, system, user))

        if system == curriculum_prompts.MATERIAL_TOPIC_SYSTEM:
            index, total, topic = CHAPTER_HEADING.search(user).groups()
            self.chapters.append((int(index), int(total), topic))
            self.chapter_prompts.append(user)
            if int(index) in self.fail_chapters:
                # Once: a retry of the same job has to be able to get past it.
                self.fail_chapters.discard(int(index))
                raise llm.LLMError("could not reach Ollama")
            for chunk in _chunks(CHAPTER_TEXT):
                yield chunk
            yield f"\n<!-- established: {topic.lower()}; term -->"
            return

        if system.startswith(curriculum_prompts.PLAN_SYSTEM[:40]):
            text = PLAN_TEXT
        elif system.startswith(curriculum_prompts.REFERENCES_SYSTEM[:40]):
            text = REFERENCES_TEXT
        elif system.startswith(curriculum_prompts.MATERIAL_SYSTEM[:40]):
            text = MATERIAL_TEXT
        else:
            text = "Refined text.\n"  # the slide refine prompts

        for chunk in _chunks(text):
            yield chunk

    # ── helpers for assertions ───────────────────────────────────────────────

    def systems(self, kind=None):
        return [system for k, _, system, _ in self.calls if kind is None or k == kind]

    def chapter_topics(self):
        return [topic for _, _, topic in self.chapters]


def _system(messages):
    return next((m.get("content", "") for m in messages if m.get("role") == "system"), "")


def _user(messages):
    content = next((m.get("content") for m in messages if m.get("role") == "user"), "")
    # OCR sends a list of parts rather than a string.
    return content if isinstance(content, str) else str(content)


def _chunks(text):
    """Stream in pieces, so `_stream_to_file` is exercised the way Ollama drives it."""
    return [text[i:i + 8] for i in range(0, len(text), 8)]


@pytest.fixture(autouse=True)
def clean_jobs():
    """Every test starts with no jobs.

    Not just tidiness: the OCR cache scans *completed* jobs, so a leftover from an
    earlier test would silently turn the next one's OCR into a no-op.
    """
    _wipe()
    yield
    _wipe()


def _wipe():
    for directory in paths.JOBS_DIR.glob("*"):
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_presets():
    """Every test starts with no presets, so a leftover cannot skew another's listing."""
    _wipe_presets()
    yield
    _wipe_presets()


def _wipe_presets():
    for directory in paths.PRESETS_DIR.glob("*"):
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    for name in ("list_models", "unload", "complete", "complete_json", "stream_chat"):
        monkeypatch.setattr(llm, name, getattr(fake, name))
    return fake


@pytest.fixture
def progress_log(monkeypatch):
    """Every (stage, current, total) the run recorded, in order.

    Polling for these would race; the repository sees all of them.
    """
    from app.repositories._job import JobRepository

    entries = []
    original = JobRepository.set_progress

    def spy(self, id, stage, current, total):
        entries.append((stage, current, total))
        return original(self, id, stage, current, total)

    monkeypatch.setattr(JobRepository, "set_progress", spy)
    return entries


@pytest.fixture
def client():
    """The real app, including the lifespan — so the worker actually runs jobs."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def pdf(tmp_path):
    """A real PDF. Page sizes differ per call, so two fixtures never share a digest."""
    counter = iter(range(100))

    def make(pages=3, name="deck.pdf"):
        offset = next(counter) * 13
        document = pdfium.PdfDocument.new()
        for page in range(pages):
            document.new_page(300 + offset + page, 400 + offset)
        path = tmp_path / name
        document.save(path)
        return path

    return make


def wait_for(client, service, job_id, timeout=30):
    """Poll a job until it is terminal, the way a client has to."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/{service}/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never finished: {job['status']}")
