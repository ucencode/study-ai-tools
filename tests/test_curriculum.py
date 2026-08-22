"""The curriculum pipeline, and the things full mode is careful about."""

import pytest
from conftest import TOPICS, wait_for

from app.core.prompts import curriculum_generator as prompts

SERVICE = "curriculum-generator"

SYLLABUS = "CS4400 Database Systems. Relational model, transactions, locking, isolation."


def submit(client, **body):
    payload = {"curriculum": SYLLABUS, "model": "gpt-oss:20b", **body}
    return client.post(f"/api/{SERVICE}/jobs", json=payload)


def run(client, **body):
    response = submit(client, **body)
    assert response.status_code == 202, response.text
    job = wait_for(client, SERVICE, response.json()["id"], timeout=60)
    return job


def test_short_mode_never_reaches_chapters(client, fake_llm, progress_log):
    job = run(client, mode="short")

    assert job["status"] == "completed", job["error"]
    assert [stage for stage, _, _ in progress_log] == [
        "metadata", "plan", "outline", "material", "references", "references",
    ]
    assert job["chapters"] == []
    assert prompts.MATERIAL_TOPIC_SYSTEM not in fake_llm.systems("stream_chat")
    assert job["result"]["course_code"] == "CS4400"


def test_full_mode_makes_exactly_one_call_per_chapter(client, fake_llm, progress_log):
    job = run(client, mode="full")

    assert job["status"] == "completed", job["error"]
    assert fake_llm.chapter_topics() == TOPICS
    assert [stage for stage, _, _ in progress_log] == [
        "metadata", "plan", "outline", "chapters", "chapters", "chapters", "chapters",
        "chapters",
    ]
    assert [chapter["topic"] for chapter in job["chapters"]] == TOPICS
    # The two are branches: full mode must never make the one-pass material call.
    assert prompts.MATERIAL_SYSTEM not in fake_llm.systems("stream_chat")


def test_the_established_ledger_is_stored_and_stripped(client, fake_llm):
    job = run(client, mode="full")

    assert all(chapter["established"] for chapter in job["chapters"])
    assert job["chapters"][0]["established"][0] == TOPICS[0].lower()

    document = client.get(f"/api/{SERVICE}/jobs/{job['id']}/output").json()["content"]
    assert "<!-- established:" not in document


def test_every_chapter_shares_one_byte_identical_prefix(client, fake_llm):
    """Ollama's prefix cache only hits on an exact match, so anything varying above
    the stable block silently doubles the cost of full mode."""
    job = run(client, mode="full")

    expected = prompts.MATERIAL_TOPIC_STABLE.format(
        lang_name="the same language as the source content",
        total=len(TOPICS),
        course="Database Systems",
        assessment="",
        topic_sequence="\n".join(f"{i + 1}. {t}" for i, t in enumerate(TOPICS)),
    )

    assert len(fake_llm.chapter_prompts) == len(TOPICS)
    for prompt in fake_llm.chapter_prompts:
        assert prompt.startswith(expected)


def test_a_dependency_is_declared_once_and_named_to_the_chapter(client, fake_llm):
    run(client, mode="full")

    first, second, fourth = (fake_llm.chapter_prompts[i] for i in (0, 1, 3))
    assert "stands on its own" in first
    assert TOPICS[0] in second.split("---", 1)[1]          # named to the chapter that needs it
    assert TOPICS[1] in fourth and TOPICS[2] in fourth
    # It is told what earlier chapters established, so it never re-derives them.
    assert f"established: {TOPICS[1].lower()}" in fourth


def test_retry_resumes_at_the_chapter_that_failed(client, fake_llm):
    fake_llm.fail_chapters = {3}

    failed = run(client, mode="full")
    assert failed["status"] == "failed"
    assert failed["error"].startswith("LLMError:")
    assert [c["topic"] for c in failed["chapters"]] == TOPICS[:2]

    response = client.post(f"/api/{SERVICE}/jobs/{failed['id']}/retry")
    assert response.status_code == 202
    resumed = wait_for(client, SERVICE, failed["id"], timeout=60)

    assert resumed["id"] == failed["id"]
    assert resumed["status"] == "completed", resumed["error"]
    assert [c["topic"] for c in resumed["chapters"]] == TOPICS
    # Chapters 1 and 2 were kept: only 3 and 4 were written on the second run.
    assert fake_llm.chapter_topics() == TOPICS[:3] + TOPICS[2:]


def test_metadata_plan_and_outline_survive_a_retry(client, fake_llm):
    fake_llm.fail_chapters = {1}

    failed = run(client, mode="full")
    assert failed["status"] == "failed"
    before = len([system for system in fake_llm.systems("complete_json")])

    client.post(f"/api/{SERVICE}/jobs/{failed['id']}/retry")
    wait_for(client, SERVICE, failed["id"], timeout=60)

    # No second metadata or outline call: the record already had both.
    assert len(fake_llm.systems("complete_json")) == before
    assert sum(1 for s in fake_llm.systems("stream_chat")
               if s.startswith(prompts.PLAN_SYSTEM[:40])) == 1


@pytest.mark.parametrize("include_plan", [True, False])
def test_the_plan_is_always_generated_but_not_always_included(client, fake_llm, include_plan):
    job = run(client, mode="short", include_plan=include_plan)
    document = client.get(f"/api/{SERVICE}/jobs/{job['id']}/output").json()["content"]

    assert sum(1 for s in fake_llm.systems("stream_chat")
               if s.startswith(prompts.PLAN_SYSTEM[:40])) == 1
    assert ("## Week 1" in document) is include_plan


def test_the_outline_drops_forward_and_invented_dependencies(client, fake_llm):
    fake_llm.outline = [
        {"topic": "A", "scope": "", "depends_on": ["B"]},          # forward reference
        {"topic": "B", "scope": "", "depends_on": ["A", "Ghost"]}, # one real, one invented
    ]

    job = run(client, mode="full")

    assert [entry["depends_on"] for entry in job["outline"]] == [[], ["A"]]


def test_an_unusable_outline_falls_back_to_the_metadata_topics(client, fake_llm):
    fake_llm.outline = []

    job = run(client, mode="full")

    assert [entry["topic"] for entry in job["outline"]] == TOPICS


def test_the_quiz_is_a_separate_call_from_the_job(client, fake_llm):
    quiz = client.post(f"/api/{SERVICE}/quiz",
                       json={"curriculum": SYLLABUS, "model": "gpt-oss:20b"})

    assert quiz.status_code == 200
    body = quiz.json()
    assert [question["id"] for question in body["questions"]] == [1, 2]
    assert body["topics"] == TOPICS

    job = run(client, questions=body["questions"],
              answers=[{"id": 1, "known": True}, {"id": 2, "known": False}])
    assert job["params"]["answers"] == [{"id": 1, "known": True}, {"id": 2, "known": False}]
