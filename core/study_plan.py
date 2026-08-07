"""Curriculum → self-study plan / study material, as async streaming pipelines.

The entry point is :func:`generate`, an async generator that yields
:class:`~core.events.StreamEvent` values. Text arrives as ``token`` events the
moment the model emits it; everything the CLI used to print goes out as
``status`` events. Both the CLI and the SSE endpoint just consume this.
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import AsyncIterator, Iterable, Sequence

from core import events as ev
from core import llm, storage
from core.languages import LANG_INSTRUCTION
from core.prompts_study_plan import (
    ASSESS_SYSTEM,
    ASSESS_USER,
    CHAIN_SUMMARY_SYSTEM,
    CHAIN_SUMMARY_USER,
    MATERIAL_SYSTEM,
    MATERIAL_TOPIC_SYSTEM,
    MATERIAL_TOPIC_USER,
    MATERIAL_USER,
    META_SYSTEM,
    META_USER,
    PLAN_SYSTEM,
    PLAN_USER,
    TOPIC_EXTRACT_SYSTEM,
    TOPIC_EXTRACT_USER,
)

MODEL_KEYWORDS = ["llama3", "qwen3", "gemma", "mistral", "deepseek", "phi", "gpt-oss"]
MODES = ("plan", "full", "book")

_ASSESSMENT_HINT = (
    "\n\n---\nLearner Assessment (use this to calibrate depth and focus):\n{summary}"
)
_MATERIAL_ASSESSMENT_HINT = (
    "\n\n---\nLearner Assessment (use this to calibrate depth — skip basics on topics "
    "already known, go deeper on unknown ones):\n{summary}"
)


async def list_models() -> list[str]:
    return await llm.list_models(MODEL_KEYWORDS)


# ── call 1: frontmatter (json, no stream) ─────────────────────────────────────

async def extract_metadata(raw: str, model: str, mode: str) -> tuple[str, list[str], dict]:
    """Returns (yaml frontmatter, topic list, raw metadata dict)."""
    data = await llm.complete_json(
        model=model,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
        messages=[
            {"role": "system", "content": META_SYSTEM},
            {"role": "user",   "content": META_USER.format(raw=raw)},
        ],
    )
    if not isinstance(data, dict):
        raise llm.LLMError("curriculum metadata was not a JSON object")

    topics = [str(t) for t in data.get("topics", []) if t]

    # injected fixed fields — never left to the model
    data["generated_on"] = datetime.now().isoformat(timespec="seconds")
    data["model"] = model
    data["mode"] = mode

    return storage.dict_to_yaml(data), topics, data


# ── assessment ────────────────────────────────────────────────────────────────

def question_count(topic_count: int) -> int:
    """Sturges' rule — enough questions to sample the curriculum, not exhaust the learner."""
    if topic_count <= 1:
        return 1
    return max(1, math.ceil(1 + 3.3 * math.log10(topic_count)))


async def build_assessment(raw: str, topics: Sequence[str], model: str) -> list[dict]:
    """Generate the yes/no familiarity questions. Returns [] if the model misbehaves."""
    num_q = question_count(len(topics))
    try:
        questions = await llm.complete_json(
            model=model,
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
            messages=[
                {"role": "system", "content": ASSESS_SYSTEM},
                {"role": "user", "content": ASSESS_USER.format(
                    raw=raw, topics=", ".join(topics), num_q=num_q,
                )},
            ],
        )
    except llm.LLMError:
        return []

    if not isinstance(questions, list):
        return []

    normalized = []
    for i, q in enumerate(questions[:num_q], 1):  # trim in case the model drifts
        if not isinstance(q, dict) or not q.get("question"):
            continue
        normalized.append({
            "id": q.get("id", i),
            "topic": str(q.get("topic", "")),
            "question": str(q["question"]),
        })
    return normalized


def summarize_assessment(questions: Iterable[dict], known_ids: Iterable) -> str:
    """Fold answered questions into the prompt fragment the generators consume."""
    known_set = {str(i) for i in known_ids}
    questions = list(questions)
    if not questions:
        return ""

    known = [q for q in questions if str(q.get("id")) in known_set]
    unknown = [q for q in questions if str(q.get("id")) not in known_set]

    lines = [f"Learner familiarity: {len(known)}/{len(questions)} topics already known."]
    if known:
        lines.append("Already familiar with:")
        lines += [f"  - [{q.get('topic', '')}] {q['question']}" for q in known]
    if unknown:
        lines.append("Not yet familiar with:")
        lines += [f"  - [{q.get('topic', '')}] {q['question']}" for q in unknown]
    return "\n".join(lines)


# ── call 2: study plan (streaming) ────────────────────────────────────────────

async def _stream_plan(raw: str, lang: str, model: str, assessment_summary: str) -> AsyncIterator:
    user_content = PLAN_USER.format(lang_name=LANG_INSTRUCTION[lang], raw=raw)
    if assessment_summary:
        user_content += _ASSESSMENT_HINT.format(summary=assessment_summary)

    async for chunk in llm.stream_chat(
        model=model,
        options={"temperature": 0.4, "num_ctx": 32768, "num_predict": 65536},
        messages=[
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
    ):
        yield chunk


# ── call 2b: topic extraction from plan (json, no stream) ─────────────────────

async def extract_topics_from_plan(plan_body: str, model: str) -> list[str]:
    """Expanded topic list the plan actually covers. Empty list on failure."""
    try:
        topics = await llm.complete_json(
            model=model,
            options={"temperature": 0, "num_ctx": 32768, "num_predict": 2048},
            messages=[
                {"role": "system", "content": TOPIC_EXTRACT_SYSTEM},
                {"role": "user",   "content": TOPIC_EXTRACT_USER.format(plan=plan_body)},
            ],
        )
    except llm.LLMError:
        return []
    if not isinstance(topics, list):
        return []
    return [str(t) for t in topics if t]


# ── call 3: study material, single pass (streaming) ───────────────────────────

async def _stream_material(raw: str, topics: Sequence[str], lang: str, model: str,
                           assessment_summary: str) -> AsyncIterator:
    user_content = MATERIAL_USER.format(
        lang_name=LANG_INSTRUCTION[lang],
        topics="\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics)),
        raw=raw,
    )
    if assessment_summary:
        user_content += _MATERIAL_ASSESSMENT_HINT.format(summary=assessment_summary)

    async for chunk in llm.stream_chat(
        model=model,
        options={"temperature": 0.3, "num_ctx": 65536, "num_predict": 131072},
        messages=[
            {"role": "system", "content": MATERIAL_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
    ):
        yield chunk


# ── call 3b: book mode — chained per-topic chapters (streaming) + digest ──────

async def _stream_book_chapter(topic: str, index: int, total: int, topic_names: Sequence[str],
                               raw: str, lang: str, model: str, assessment_summary: str,
                               chain_digest: Sequence[dict]) -> AsyncIterator:
    topic_sequence = "\n".join(
        f"{i + 1}. {t}" + ("  ← YOU ARE WRITING THIS ONE" if i == index - 1 else "")
        for i, t in enumerate(topic_names)
    )

    chain_context = ""
    digest_lines = "\n".join(
        f"{i + 1}. {d['topic']} — {d['digest']}"
        for i, d in enumerate(chain_digest) if d.get("digest")
    )
    if digest_lines:
        chain_context = (
            "Digest of chapters already covered (do not repeat these explanations; build on them):\n"
            f"{digest_lines}\n\n"
        )

    user_content = MATERIAL_TOPIC_USER.format(
        lang_name=LANG_INSTRUCTION[lang],
        index=index,
        total=total,
        topic_sequence=topic_sequence,
        chain_context=chain_context,
        topic=topic,
        raw=raw,
    )
    if assessment_summary:
        user_content += _MATERIAL_ASSESSMENT_HINT.format(summary=assessment_summary)

    async for chunk in llm.stream_chat(
        model=model,
        options={"temperature": 0.3, "num_ctx": 32768, "num_predict": 16384},
        messages=[
            {"role": "system", "content": MATERIAL_TOPIC_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
    ):
        yield chunk


async def _digest_chapter(topic: str, body: str, model: str) -> str:
    """2-3 sentence digest so the next chapter can build on this one."""
    try:
        digest = await llm.complete(
            model=model,
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 300},
            messages=[
                {"role": "system", "content": CHAIN_SUMMARY_SYSTEM},
                {"role": "user",   "content": CHAIN_SUMMARY_USER.format(topic=topic, body=body)},
            ],
        )
        return digest.strip()
    except llm.LLMError:
        return ""


# ── the pipeline ──────────────────────────────────────────────────────────────

async def generate(
    *,
    raw: str,
    source_name: str,
    model: str,
    lang: str,
    mode: str,
    assessment_summary: str = "",
    use_cache: bool = True,
    fresh: bool = False,
    metadata: tuple[str, list[str]] | None = None,
) -> AsyncIterator[ev.StreamEvent]:
    """Run the full curriculum pipeline, streaming every stage.

    `mode` is one of "plan" (plan only), "full" (plan + material in one pass) or
    "book" (plan + one chained chapter per topic, saved after every chapter so an
    interrupted run resumes where it left off).

    Pass `metadata` as an already-extracted (frontmatter, topics) pair to skip
    the metadata call — the CLI has one in hand from building the assessment.
    """
    if mode not in MODES:
        yield ev.error(f"unknown mode '{mode}' — expected one of {', '.join(MODES)}")
        return
    if lang not in LANG_INSTRUCTION:
        yield ev.error(f"unknown language '{lang}'")
        return

    lang_name = LANG_INSTRUCTION[lang]

    if use_cache:
        cached = storage.find_cached_plan(source_name, model, lang, mode)
        if cached:
            yield ev.status(f"found existing output: {cached.name}", stage="cache")
            yield ev.done(path=str(cached), name=cached.name,
                          tool="study-plan-generatinator", cached=True)
            return

    # book mode — pick up an interrupted run rather than paying for it twice
    partial_file = storage.partial_path(source_name, model, lang)
    partial_state: dict | None = None
    resumed = False
    if mode == "book":
        if fresh:
            storage.delete_partial(partial_file)
        else:
            loaded = storage.load_partial(partial_file)
            if loaded and loaded.get("source") == source_name:
                done_n, total_n = len(loaded["completed"]), len(loaded["material_topics"])
                if done_n < total_n:
                    partial_state = loaded
                    resumed = True
                    yield ev.status(
                        f"resuming: {done_n}/{total_n} chapters already written",
                        stage="book",
                    )

    try:
        if resumed and partial_state is not None:
            frontmatter        = partial_state["frontmatter"]
            assessment_summary = partial_state["assessment_summary"]
            plan_body          = partial_state["plan_body"]
            material_topics    = partial_state["material_topics"]
            topics             = material_topics
            yield ev.meta(frontmatter=frontmatter, topics=topics, resumed=True)
        else:
            # call 1 — frontmatter (fast, no stream)
            if metadata is not None:
                frontmatter, topics = metadata
            else:
                yield ev.status("extracting curriculum metadata...", stage="meta")
                started = time.time()
                frontmatter, topics, _ = await extract_metadata(raw, model, mode)
                yield ev.status(f"metadata ready ({time.time() - started:.2f}s)", stage="meta")
            yield ev.meta(frontmatter=frontmatter, topics=topics)

            # call 2 — study plan (streaming)
            yield ev.status(f"model={model} lang={lang_name}", stage="plan")
            yield ev.section("plan", "Study Plan")
            started = time.time()
            chunks: list[str] = []
            async for chunk in _stream_plan(raw, lang, model, assessment_summary):
                chunks.append(chunk)
                yield ev.token(chunk)
            plan_body = "".join(chunks)
            yield ev.status(
                f"plan done ({time.time() - started:.2f}s, {len(plan_body)} chars)", stage="plan",
            )
            material_topics = []

        sections: list[tuple[str, str]] = []
        if assessment_summary:
            sections.append(("Learner Assessment", assessment_summary))
        sections.append(("Study Plan", plan_body))

        if mode == "full":
            yield ev.status("extracting expanded topic list...", stage="topics")
            expanded = await extract_topics_from_plan(plan_body, model)
            material_topics = expanded or topics
            yield ev.status(f"{len(material_topics)} topics", stage="topics")
            yield ev.meta(material_topics=material_topics)

            yield ev.status(f"writing material for {len(material_topics)} topics", stage="material")
            yield ev.section("material", "Study Material")
            started = time.time()
            chunks = []
            async for chunk in _stream_material(raw, material_topics, lang, model, assessment_summary):
                chunks.append(chunk)
                yield ev.token(chunk)
            material_body = "".join(chunks)
            yield ev.status(
                f"material done ({time.time() - started:.2f}s, {len(material_body)} chars)",
                stage="material",
            )
            sections.append(("Study Material", material_body))

        elif mode == "book":
            if not resumed:
                yield ev.status("extracting expanded topic list...", stage="topics")
                expanded = await extract_topics_from_plan(plan_body, model)
                material_topics = expanded or topics
                yield ev.status(f"{len(material_topics)} chapters to write", stage="topics")
                yield ev.meta(material_topics=material_topics)
                partial_state = {
                    "source": source_name,
                    "model": model,
                    "lang": lang,
                    "frontmatter": frontmatter,
                    "assessment_summary": assessment_summary,
                    "plan_body": plan_body,
                    "material_topics": material_topics,
                    "completed": [],
                }
                storage.save_partial(partial_file, partial_state)

            assert partial_state is not None
            completed = partial_state["completed"]
            total = len(material_topics)
            durations = [e["duration"] for e in completed if "duration" in e]

            # already-written chapters, replayed so a resumed run still renders whole
            for i, entry in enumerate(completed, 1):
                yield ev.section(f"chapter-{i}", f"Chapter {i}/{total}: {entry['topic']}", restored=True)
                yield ev.token(entry["body"])

            run_start = time.time()
            for index in range(len(completed) + 1, total + 1):
                topic = material_topics[index - 1]

                if durations:
                    avg = sum(durations) / len(durations)
                    eta = avg * (total - index + 1)
                    yield ev.status(
                        f"{len(completed)}/{total} done — est. {storage.format_duration(eta)} "
                        f"remaining (avg {storage.format_duration(avg)}/chapter)",
                        stage="book", completed=len(completed), total=total,
                    )

                yield ev.section(f"chapter-{index}", f"Chapter {index}/{total}: {topic}")
                chapter_start = time.time()
                chunks = []
                async for chunk in _stream_book_chapter(
                    topic, index, total, material_topics, raw, lang, model,
                    assessment_summary, completed,
                ):
                    chunks.append(chunk)
                    yield ev.token(chunk)
                body = "".join(chunks)

                yield ev.status(f'digesting "{topic}" for chaining...', stage="book")
                digest = await _digest_chapter(topic, body, model)

                duration = time.time() - chapter_start
                durations.append(duration)
                completed.append({"topic": topic, "body": body, "digest": digest,
                                  "duration": duration})
                storage.save_partial(partial_file, partial_state)
                yield ev.status(
                    f"chapter {index}/{total} done ({storage.format_duration(duration)})",
                    stage="book", completed=len(completed), total=total,
                )

            yield ev.status(
                f"all {total} chapters complete ({storage.format_duration(time.time() - run_start)} this session)",
                stage="book",
            )
            sections.append(("Study Material", "\n\n".join(e["body"] for e in completed)))
            storage.delete_partial(partial_file)

    except llm.LLMError as e:
        yield ev.error(str(e))
        return

    await llm.unload(model)
    path = storage.save_plan(frontmatter, sections, source_name=source_name, lang=lang, mode=mode)
    yield ev.status(f"saved → {path}", stage="output")
    yield ev.done(path=str(path), name=path.name, tool="study-plan-generatinator", cached=False)
