#!/usr/bin/env python3

import os
import re
import json
import math
import subprocess
import argparse
import time
from datetime import datetime
from pathlib import Path
from ollama import chat, ChatResponse


# ── constants ─────────────────────────────────────────────────────────────────

MODEL_KEYWORDS = ["llama3", "qwen3", "gemma", "mistral", "deepseek", "phi", "gpt-oss"]

LANG_INSTRUCTION = {
    "auto": "the same language as the source content",
    "ar": "العربية (Arabic)",
    "de": "Deutsch (German)",
    "en": "English",
    "es": "Español (Spanish)",
    "fi": "Suomi (Finnish)",
    "fr": "Français (French)",
    "hi": "हिन्दी (Hindi)",
    "id": "Bahasa Indonesia",
    "it": "Italiano (Italian)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "nl": "Nederlands (Dutch)",
    "pl": "Polski (Polish)",
    "pt": "Português (Portuguese)",
    "ru": "Русский (Russian)",
    "sv": "Svenska (Swedish)",
    "th": "ภาษาไทย (Thai)",
    "tr": "Türkçe (Turkish)",
    "uk": "Українська (Ukrainian)",
    "vi": "Tiếng Việt (Vietnamese)",
    "zh": "简体中文 (Chinese)",
}

LANG_EXPERIMENTAL = {
    "ja", "ko", "it", "nl", "pl", "tr",
    "hi", "vi", "uk", "fi", "sv", "th",
}

MODES = ("plan", "full", "book")

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs" / "study-plan-generatinator"
INPUT_DIR  = Path(__file__).parent.parent.parent / "inputs"


# ── system prompts ────────────────────────────────────────────────────────────

META_SYSTEM = """\
You are a curriculum metadata extractor.

Extract structured metadata from the curriculum text the user provides.
Return ONLY a valid JSON object with exactly these fields:

{
  "title":           "string  — e.g. 'Self-Study Plan: Calculus'",
  "course":          "string  — normalized course name, title case",
  "course_code":     "string  — if explicitly present (e.g. CS101), else empty string",
  "credits":         "integer — 0 if not found",
  "topics":          ["list of topic strings"],
  "outcomes":        ["list of learning outcome strings"],
  "topics_count":    "integer",
  "outcomes_count":  "integer",
  "estimated_weeks": "integer — roughly topics_count * 1.5, rounded",
  "tags":            ["2-4 lowercase subject area keywords"],
  "status":          "draft"
}

Rules:
- Normalize course name to title case
- title field must follow pattern: "Self-Study Plan: <Course Name>"
- course_code only if explicitly present, else empty string
- "topics" must contain ONLY subject-matter concepts the learner will study and practice.
  Exclude proficiency frameworks, assessment scales/rubrics, grading criteria, learning
  objectives, course structure, or administrative procedures — even if the curriculum
  text lists them alongside real topics.
  Example of bad topic entries: "CEFR Proficiency Levels", "Grading Rubric", "Course Assessment Criteria"
- Raw JSON only — no explanation, no markdown fences, no preamble"""

META_USER = "Extract metadata from this curriculum:\n\n{raw}"

PLAN_SYSTEM = """\
You are a study plan architect for a self-directed learner.

Learner context:
- Works a full-time job; studies on weekday evenings (~1-2 hrs) and weekends (~4 hrs)
- Has a software engineering background: advanced in backend, basic in frontend
- For topics outside software engineering, assume beginner level
- Does NOT trust surface-level explanations — wants real conceptual understanding
- Attends formal classes but treats them only as a loose reference
- Goal: genuine mastery, not just passing exams

Output rules:
- Format: Markdown only
- Do NOT include YAML frontmatter — it is prepended separately
- Do NOT use tables anywhere in the output — not for schedules, topics, resources, or any other content
- Use headings, bullet points, and plain prose only
- Structure:
    1. Realistic weekly schedule with hours/week breakdown — write as a plain list (e.g. "Mon–Thu: 1.5 hrs — focused study")
    2. Phase-by-phase topic breakdown with estimated weeks per phase
    3. Per topic: what to focus on, what to skip, and a "you understand this when..." checkpoint
    4. Recommended free resources — specific titles only, no generic advice
    5. Weekly review ritual to consolidate learning
- At the end of EVERY phase, include this exact block:

> **Go Deeper** *(optional)*
> - <Specific book title + chapter, or named concept, or harder problem set>
> - <Second recommendation>
> - <Third recommendation, if relevant>
> *Pursue these only if you want to go beyond the phase scope.*

- Write in the student's frame, not the curriculum's: name the actual concepts, operations, and techniques — never echo abstract syllabus language like "understand X" or "explore Y". Translate each topic into what the learner must concretely be able to do, derive, prove, implement, or explain to someone else.
- Be direct and opinionated; skip hedging and filler
- Assume the learner is intelligent but time-constrained"""

PLAN_USER = "Respond in {lang_name}.\n\nCurriculum:\n\"\"\"\n{raw}\n\"\"\""

MATERIAL_SYSTEM = """\
You are a technical study material writer for a self-directed learner.

Learner context:
- Works a full-time job; limited study time — material must be dense, not padded
- Has a software engineering background: advanced in backend, basic in frontend
- For topics outside software engineering, assume beginner level and build from first principles
- Wants real understanding, not surface definitions
- Will use this material alongside a study plan, so assume topic order is intentional
- Calibrate depth accordingly: skip basics the learner already knows for SE topics,
  but do not skip foundational explanation for non-SE topics

Output rules:
- Format: Markdown only
- Do NOT include YAML frontmatter
- Write every topic using EXACTLY this template, in this order, with these exact headings:

---
## <Topic Name>

### Concept & Intuition
Explain the core idea. Build intuition first, then formalize.
Cover the "why this exists" before the "how it works".
Use analogies only where they genuinely clarify.

### Worked Examples
Minimum 2 worked examples, stepped through clearly.
Show reasoning at each step, not just the mechanics.

### Practice Problems
3-5 problems of increasing difficulty. No solutions.
Last problem must stretch beyond routine application.

### Common Misconceptions
2-3 specific wrong mental models people bring INTO this topic.
State the misconception explicitly, then correct it precisely.
No generic warnings — name the exact flawed assumption.

### Go Deeper *(optional — pursue only if curious)*
2-4 concrete recommendations for going beyond this topic.
Each entry must name: a specific book + chapter, a named theorem,
a specific paper, or a precisely described problem class.
No generic advice like "read more about X".
---

- Repeat this exact structure for every topic, in the order listed
- Be precise and direct; no filler, no repetition across topics
- Assume the learner is intelligent but time-constrained"""

MATERIAL_USER = """\
Respond in {lang_name}.

Write study material for every topic in this curriculum, in the order listed:

{topics}

Curriculum context (for depth calibration):
\"\"\"
{raw}
\"\"\""""

MATERIAL_TOPIC_SYSTEM = """\
You are a technical study material writer for a self-directed learner, writing ONE chapter \
at a time in a sequential, book-style curriculum. Each chapter must read as though it belongs \
to the same book: consistent voice, deliberate continuity, no re-explaining what earlier \
chapters already established.

Learner context:
- Works a full-time job; limited study time — material must be dense, not padded
- Has a software engineering background: advanced in backend, basic in frontend
- For topics outside software engineering, assume beginner level and build from first principles
- Wants real understanding, not surface definitions
- Calibrate depth accordingly: skip basics the learner already knows for SE topics,
  but do not skip foundational explanation for non-SE topics

Chaining rules:
- You will be given a digest of every chapter already covered. Use it to avoid re-deriving
  concepts, notation, or definitions already established — reference them by name instead
  (e.g. "using the chain rule from the previous chapter...").
- If this chapter builds directly on a prior one, open with a short "### Building On" section
  (2-4 sentences) naming exactly what it relies on. If it does NOT build on prior material,
  state that explicitly instead of forcing a false connection, and omit inventing dependencies.
- You may name chapters that come later in the sequence (the full sequence is provided) to
  foreshadow (e.g. "you'll extend this to X later"), but never assume details about their
  content since they have not been written yet.

Output rules:
- Format: Markdown only
- Do NOT include YAML frontmatter
- Write ONLY the one chapter you are asked for — do not write any other topic — using
  EXACTLY this template, in this order, with these exact headings:

---
## <Topic Name>

### Building On *(omit this entire section if this is the first chapter or there is no real dependency)*
2-4 sentences naming exactly which prior chapter(s)/concepts this one builds on.

### Concept & Intuition
Explain the core idea. Build intuition first, then formalize.
Cover the "why this exists" before the "how it works".
Use analogies only where they genuinely clarify.

### Worked Examples
Minimum 2 worked examples, stepped through clearly.
Show reasoning at each step, not just the mechanics.

### Practice Problems
3-5 problems of increasing difficulty. No solutions.
Last problem must stretch beyond routine application.

### Common Misconceptions
2-3 specific wrong mental models people bring INTO this topic.
State the misconception explicitly, then correct it precisely.
No generic warnings — name the exact flawed assumption.

### Go Deeper *(optional — pursue only if curious)*
2-4 concrete recommendations for going beyond this topic.
Each entry must name: a specific book + chapter, a named theorem,
a specific paper, or a precisely described problem class.
No generic advice like "read more about X".
---

- Be precise and direct; no filler, no repetition of earlier chapters
- Write comprehensively — this is a full book chapter, not a summary. Favor depth (more
  worked examples, fuller derivations, richer misconception coverage) over brevity.
- Assume the learner is intelligent but time-constrained"""

MATERIAL_TOPIC_USER = """\
Respond in {lang_name}.

This is chapter {index} of {total} in a sequential study curriculum.

Full chapter sequence:
{topic_sequence}

{chain_context}Write comprehensive, book-style study material for this chapter only:
"{topic}"

Curriculum context (for depth calibration):
\"\"\"
{raw}
\"\"\""""

CHAIN_SUMMARY_SYSTEM = """\
You are a study-chapter digest writer.

Given the full text of one chapter from a study-material book, produce a 2-3 sentence \
digest capturing: the core concept(s) it established, any key terms/notation it introduced, \
and what the learner should now know entering the next chapter.

Output ONLY the digest as plain text — no headings, no markdown, no preamble, no quotes."""

CHAIN_SUMMARY_USER = """\
Chapter: {topic}

Chapter text:
\"\"\"
{body}
\"\"\""""

TOPIC_EXTRACT_SYSTEM = """\
You are a topic list extractor.

Given a study plan in Markdown, extract a flat, ordered list of every distinct topic
and subtopic the plan covers — including any the plan adds beyond the raw curriculum.

Return ONLY a valid JSON array of strings, one entry per topic, in the order they appear.
No explanations, no markdown fences, no nesting."""

TOPIC_EXTRACT_USER = "Extract the topic list from this study plan:\n\n{plan}"

ASSESS_SYSTEM = """\
You are a curriculum familiarity assessor.
Given a course curriculum and a target question count, generate exactly that many \
yes/no self-assessment questions to check what the learner already knows.

STRICT RULE — what to ask about:
  Ask ONLY about subject-matter concepts the learner will study and practice.
  Example (language course): "Do you know how to conjugate verbs in the past tense?"
  Example (math course): "Are you familiar with the chain rule in differentiation?"

STRICT RULE — what NEVER to ask about:
  Do NOT ask about proficiency frameworks, assessment scales, grading rubrics,
  learning objectives, curriculum structure, course design, administrative procedures,
  or how the course itself is organized.
  Bad example: "Do you know the four UN language proficiency levels?"
  Bad example: "Are you familiar with how this course assesses speaking skills?"

Output ONLY a JSON array. No explanation, no markdown fences, no extra text.

Each element must have exactly these keys:
[
  {
    "id": 1,
    "topic": "<topic name this question covers>",
    "question": "Do you know ...?"
  }
]

Additional rules:
- id is 1-based integer
- every question must start with "Do you know" or "Are you familiar with"
- questions must be specific — name the concept, not just the topic area
- cover a spread of topics, not just the first few"""

ASSESS_USER = """\
Curriculum:
{raw}

Topics: {topics}

Generate exactly {num_q} familiarity questions."""


# ── ollama model discovery ────────────────────────────────────────────────────

def list_models() -> list[str]:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[error] 'ollama list' failed: {result.stderr.strip()}")
        exit(1)
    models = []
    for line in result.stdout.strip().splitlines()[1:]:
        name = line.split()[0]
        if any(kw in name for kw in MODEL_KEYWORDS):
            models.append(name)
    return models


def eject_model(model: str):
    print(f"[ollama] ejecting {model}...", end=" ", flush=True)
    result = subprocess.run(["ollama", "stop", model], capture_output=True, text=True)
    print("done" if result.returncode == 0 else f"warn: {result.stderr.strip()}")


# ── interactive prompts ───────────────────────────────────────────────────────

def ask_model(models: list[str]) -> str:
    print("\nSelect model:")
    for i, m in enumerate(models, 1):
        print(f"  {i}. {m}")
    print("[default: 1]")
    choice = input(">>> ").strip() or "1"
    try:
        return models[int(choice) - 1]
    except (ValueError, IndexError):
        print(f"[warn] invalid choice, using {models[0]}")
        return models[0]


def ask_language() -> str:
    codes = list(LANG_INSTRUCTION.keys())
    print(f"\nOutput language? ({' / '.join(codes)}) [default: auto]")
    lang = input(">>> ").strip().lower() or "auto"
    if lang not in LANG_INSTRUCTION:
        print(f"[warn] unknown language '{lang}', using auto")
        return "auto"
    if lang in LANG_EXPERIMENTAL:
        print(f"[warn] '{LANG_INSTRUCTION[lang]}' quality depends on model proficiency. Results may vary.")
    return lang


def ask_mode() -> str:
    print("""
Mode?
  1. plan   — study plan only (fastest)
  2. full   — study plan + study material for all topics in one pass (fast)
  3. book   — study plan + one book-style chapter per topic, each building on the
              last (slow: 2 model calls per topic, can take 30-60+ min on large
              curricula — but safe to Ctrl+C and resume later)
[default: 1]""")
    choice = input(">>> ").strip() or "1"
    return {"1": "plan", "2": "full", "3": "book"}.get(choice, "plan")


def ask_file() -> str:
    txt_files = sorted(INPUT_DIR.glob("*.txt")) if INPUT_DIR.exists() else []
    if txt_files:
        print(f"\nCurriculum file? (found in inputs/):")
        for i, f in enumerate(txt_files, 1):
            print(f"  {i}. {f.name}")
        print("Or enter a path manually.")
    else:
        print("\nCurriculum file? (path to .txt file)")
    choice = input(">>> ").strip()
    if choice.isdigit() and txt_files:
        idx = int(choice) - 1
        if 0 <= idx < len(txt_files):
            return str(txt_files[idx])
    return choice


def _format_duration(seconds: float) -> str:
    """Render a duration as e.g. '45s', '3m12s', '1h05m' for progress/ETA messages."""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


# Sanitize JSON by removing markdown code fences if present, and trimming whitespace.
def _sanitize_json(raw: str) -> str:
    """Strip common model artifacts that break json.loads."""
    # strip markdown fences
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE)
    # strip // line comments
    raw = re.sub(r"//[^\n]*", "", raw)
    # strip # line comments (only when not inside a string — best-effort)
    raw = re.sub(r"(?<![\"'\w])#[^\n]*", "", raw)
    # strip trailing commas before ] or }
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw.strip()


# ── call 1: frontmatter (json, no stream) ─────────────────────────────────────

def generate_frontmatter(raw: str, model: str, mode: str) -> tuple[str, list[str]]:
    print(f"\n[meta] extracting curriculum metadata...", end=" ", flush=True)
    start = time.time()

    response: ChatResponse = chat(
        model=model,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
        messages=[
            {"role": "system", "content": META_SYSTEM},
            {"role": "user",   "content": META_USER.format(raw=raw)},
        ],
    )

    raw_json = _sanitize_json(response.message.content)
    print(f"done ({time.time() - start:.2f}s)")

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"[error] frontmatter JSON parse failed: {e}")
        print(f"[debug] raw response:\n{raw_json}")
        exit(1)

    topics = data.get("topics", [])

    # inject fixed fields — never left to model
    data["generated_on"] = datetime.now().isoformat(timespec="seconds")
    data["model"]        = model
    data["mode"]         = mode

    return _dict_to_yaml(data), topics


def _dict_to_yaml(data: dict) -> str:
    lines = ["---"]
    for key, val in data.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f'  - "{item}"')
        elif isinstance(val, bool):
            lines.append(f"{key}: {str(val).lower()}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key}: {val}")
        else:
            lines.append(f'{key}: "{str(val).replace(chr(34), chr(92)+chr(34))}"')
    lines.append("---")
    return "\n".join(lines) + "\n"


# ── call 2: study plan (streaming) ───────────────────────────────────────────

def generate_plan(raw: str, lang: str, model: str, assessment_summary: str = "") -> str:
    lang_name = LANG_INSTRUCTION[lang]
    print(f"\n[plan] model={model} lang={lang_name}")
    print(f"[plan] streaming...\n")
    print("-" * 56)

    user_content = PLAN_USER.format(lang_name=lang_name, raw=raw)
    if assessment_summary:
        user_content += f"\n\n---\nLearner Assessment (use this to calibrate depth and focus):\n{assessment_summary}"

    start = time.time()
    chunks = []
    stream = chat(
        model=model,
        options={"temperature": 0.4, "num_ctx": 32768, "num_predict": 65536},
        messages=[
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        stream=True,
    )

    for chunk in stream:
        token = chunk.message.content
        print(token, end="", flush=True)
        chunks.append(token)

    body = "".join(chunks)
    print(f"\n" + "-" * 56)
    print(f"[plan] done ({time.time() - start:.2f}s, {len(body)} chars)")
    return body


# ── call 2b: topic extraction from plan (json, no stream) ────────────────────

def extract_topics_from_plan(plan_body: str, model: str) -> list[str]:
    print(f"\n[topics] extracting expanded topic list...", end=" ", flush=True)
    start = time.time()

    response: ChatResponse = chat(
        model=model,
        options={"temperature": 0, "num_ctx": 32768, "num_predict": 2048},
        messages=[
            {"role": "system", "content": TOPIC_EXTRACT_SYSTEM},
            {"role": "user",   "content": TOPIC_EXTRACT_USER.format(plan=plan_body)},
        ],
    )

    raw_json = _sanitize_json(response.message.content)

    try:
        topics = json.loads(raw_json)
        if not isinstance(topics, list):
            raise ValueError("expected a JSON array")
        topics = [str(t) for t in topics if t]
        print(f"done ({time.time() - start:.2f}s)")
        print(f"[topics] {len(topics)} topics extracted")
        return topics
    except Exception as e:
        print(f"warn: {e}")
        print(f"[topics] extraction failed — falling back to raw curriculum topics")
        return []


# ── assessment: generate + interactively collect answers ─────────────────────

def run_assessment(raw: str, topics: list[str], model: str) -> str:
    n = len(topics)
    num_q = max(1, math.ceil(1 + 3.3 * math.log10(n))) if n > 1 else 1

    print(f"\n[assessment] generating {num_q} questions for {n} topics...", end=" ", flush=True)
    start = time.time()

    response: ChatResponse = chat(
        model=model,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
        messages=[
            {"role": "system", "content": ASSESS_SYSTEM},
            {"role": "user",   "content": ASSESS_USER.format(
                raw=raw,
                topics=", ".join(topics),
                num_q=num_q,
            )},
        ],
    )

    raw_json = _sanitize_json(response.message.content)
    print(f"done ({time.time() - start:.2f}s)")

    try:
        questions = json.loads(raw_json)
        if not isinstance(questions, list):
            raise ValueError("expected a JSON array")
    except Exception as e:
        print(f"[assessment] parse failed ({e}) — skipping assessment")
        return ""

    # trim to num_q in case the model drifts
    questions = questions[:num_q]

    print(f"\n[assessment] {len(questions)} questions — answer Y/N for each\n")
    known, unknown = [], []
    for q in questions:
        while True:
            ans = input(f"  {q['question']} (Y/N): ").strip().upper()
            if ans in ("Y", "N", "YES", "NO"):
                break
            print("  Please answer Y or N.")
        (known if ans.startswith("Y") else unknown).append(q)

    known_count = len(known)
    total = len(questions)
    print(f"\n[assessment] familiar with {known_count}/{total} topics")

    lines = [f"Learner familiarity: {known_count}/{total} topics already known."]
    if known:
        lines.append("Already familiar with:")
        lines += [f"  - [{q.get('topic', '')}] {q['question']}" for q in known]
    if unknown:
        lines.append("Not yet familiar with:")
        lines += [f"  - [{q.get('topic', '')}] {q['question']}" for q in unknown]

    return "\n".join(lines)


# ── call 3: study material (streaming) ───────────────────────────────────────

def generate_material(raw: str, topics: list[str], lang: str, model: str, assessment_summary: str = "") -> str:
    lang_name  = LANG_INSTRUCTION[lang]
    topics_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))

    print(f"\n[material] model={model} lang={lang_name} topics={len(topics)}")
    print(f"[material] streaming...\n")
    print("-" * 56)

    user_content = MATERIAL_USER.format(
        lang_name=lang_name,
        topics=topics_str,
        raw=raw,
    )
    if assessment_summary:
        user_content += f"\n\n---\nLearner Assessment (use this to calibrate depth — skip basics on topics already known, go deeper on unknown ones):\n{assessment_summary}"

    start = time.time()
    chunks = []
    stream = chat(
        model=model,
        options={"temperature": 0.3, "num_ctx": 65536, "num_predict": 131072},
        messages=[
            {"role": "system", "content": MATERIAL_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        stream=True,
    )

    for chunk in stream:
        token = chunk.message.content
        print(token, end="", flush=True)
        chunks.append(token)

    body = "".join(chunks)
    print(f"\n" + "-" * 56)
    print(f"[material] done ({time.time() - start:.2f}s, {len(body)} chars)")
    return body


# ── call 3b: book mode — chained per-topic chapter (streaming) + digest ──────

def summarize_topic_for_chain(topic: str, body: str, model: str) -> str:
    print(f"[book] digesting \"{topic}\" for chaining...", end=" ", flush=True)
    start = time.time()

    try:
        response: ChatResponse = chat(
            model=model,
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 300},
            messages=[
                {"role": "system", "content": CHAIN_SUMMARY_SYSTEM},
                {"role": "user",   "content": CHAIN_SUMMARY_USER.format(topic=topic, body=body)},
            ],
        )
        digest = response.message.content.strip()
        print(f"done ({time.time() - start:.2f}s)")
        return digest
    except Exception as e:
        print(f"warn: digest failed ({e}) — continuing without it")
        return ""


def generate_book_topic(topic: str, index: int, total: int, topic_names: list[str],
                        raw: str, lang: str, model: str, assessment_summary: str,
                        chain_digest: list[dict]) -> str:
    lang_name = LANG_INSTRUCTION[lang]

    topic_sequence = "\n".join(
        f"{i+1}. {t}" + ("  ← YOU ARE WRITING THIS ONE" if i == index - 1 else "")
        for i, t in enumerate(topic_names)
    )

    chain_context = ""
    if chain_digest:
        digest_lines = "\n".join(
            f"{i+1}. {d['topic']} — {d['digest']}" for i, d in enumerate(chain_digest) if d.get("digest")
        )
        if digest_lines:
            chain_context = (
                "Digest of chapters already covered (do not repeat these explanations; build on them):\n"
                f"{digest_lines}\n\n"
            )

    user_content = MATERIAL_TOPIC_USER.format(
        lang_name=lang_name,
        index=index,
        total=total,
        topic_sequence=topic_sequence,
        chain_context=chain_context,
        topic=topic,
        raw=raw,
    )
    if assessment_summary:
        user_content += f"\n\n---\nLearner Assessment (use this to calibrate depth — skip basics on topics already known, go deeper on unknown ones):\n{assessment_summary}"

    print(f"\n[book] chapter {index}/{total}: \"{topic}\" — model={model} lang={lang_name}")
    print(f"[book] streaming...\n")
    print("-" * 56)

    start = time.time()
    chunks = []
    stream = chat(
        model=model,
        options={"temperature": 0.3, "num_ctx": 32768, "num_predict": 16384},
        messages=[
            {"role": "system", "content": MATERIAL_TOPIC_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        stream=True,
    )

    for chunk in stream:
        token = chunk.message.content
        print(token, end="", flush=True)
        chunks.append(token)

    body = "".join(chunks)
    print(f"\n" + "-" * 56)
    print(f"[book] done ({time.time() - start:.2f}s, {len(body)} chars)")
    return body


def generate_book_material(raw: str, topics: list[str], lang: str, model: str,
                           assessment_summary: str, partial_state: dict, partial_file: Path) -> str:
    total     = len(topics)
    completed = partial_state["completed"]
    durations = [e["duration"] for e in completed if "duration" in e]

    if not completed:
        print(f"\n[book] {total} chapters to write with {model} — 2 model calls per chapter "
              f"(1 long write + 1 quick digest for chaining).")
        print(f"[book] progress is saved after every chapter — safe to Ctrl+C and resume later.")
    else:
        print(f"\n[book] resuming: {len(completed)}/{total} chapters already done, "
              f"{total - len(completed)} to go.")

    run_start = time.time()

    for index in range(len(completed) + 1, total + 1):
        topic = topics[index - 1]

        if durations:
            avg = sum(durations) / len(durations)
            eta = avg * (total - index + 1)
            print(f"[book] {len(completed)}/{total} done — "
                  f"est. {_format_duration(eta)} remaining (avg {_format_duration(avg)}/chapter)")

        chapter_start = time.time()
        body  = generate_book_topic(
            topic, index, total, topics, raw, lang, model, assessment_summary, completed,
        )
        digest = summarize_topic_for_chain(topic, body, model)
        duration = time.time() - chapter_start
        durations.append(duration)
        completed.append({"topic": topic, "body": body, "digest": digest, "duration": duration})
        save_partial(partial_file, partial_state)

    print(f"\n[book] all {total} chapters complete ({_format_duration(time.time() - run_start)} this session)")
    return "\n\n".join(entry["body"] for entry in completed)


# ── cache ─────────────────────────────────────────────────────────────────────

def find_cached(input_file: str, model: str, lang: str, mode: str) -> Path | None:
    output_dir = OUTPUT_DIR
    if not output_dir.exists():
        return None
    basename = os.path.basename(input_file)
    pattern  = {"plan": "*-study_plan.md", "full": "*-full.md", "book": "*-book.md"}[mode]
    for path in sorted(output_dir.glob(pattern), reverse=True):
        meta = _read_frontmatter(path)
        if (meta.get("source") == basename
                and meta.get("model") == model
                and meta.get("lang") == lang
                and meta.get("mode") == mode):
            print(f"[cache] found existing output: {path}")
            return path
    return None


def _read_frontmatter(path: Path) -> dict:
    meta = {}
    try:
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) < 3:
            return meta
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return meta


# ── partial state (book mode resume) ──────────────────────────────────────────

def partial_path(input_file: str, model: str, lang: str) -> Path:
    partial_dir = OUTPUT_DIR / ".partial"
    slug        = re.sub(r"[^\w]+", "_", Path(input_file).stem.lower()).strip("_")[:40]
    model_safe  = re.sub(r"[^\w]+", "_", model.lower()).strip("_")
    return partial_dir / f"{slug}__{model_safe}__{lang}.json"


def load_partial(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[book] warn: could not read partial file ({e}) — starting fresh")
        return None


def save_partial(path: Path, state: dict):
    os.makedirs(path.parent, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def delete_partial(path: Path):
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def ask_resume(n_done: int, n_total: int) -> bool:
    print(f"\n[book] found an in-progress run: {n_done}/{n_total} chapters already written.")
    print("Resume from where it left off? [Y/n] (n = discard it and start over)")
    ans = input(">>> ").strip().lower() or "y"
    return ans.startswith("y")


# ── output ────────────────────────────────────────────────────────────────────

def save_output(frontmatter: str, sections: list[tuple[str, str]],
                input_file: str, model: str, lang: str, mode: str) -> Path:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    slug      = re.sub(r"[^\w]+", "_", Path(input_file).stem.lower()).strip("_")[:40]
    suffix    = {"plan": "study_plan", "full": "full", "book": "book"}[mode]
    path      = OUTPUT_DIR / f"{timestamp}-{slug}-{suffix}.md"

    fm = frontmatter.rstrip().removesuffix("---")
    fm += f'\nsource: "{os.path.basename(input_file)}"\n'
    fm += f'lang: "{lang}"\n'
    fm += "---\n"

    body = "\n\n---\n\n".join(f"# {label}\n\n{content}" for label, content in sections)
    path.write_text(fm + "\n" + body, encoding="utf-8")
    print(f"[output] saved → {path}")
    return path


# ── args ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Curriculum → Self-Study Plan / Full Material")
    parser.add_argument("file",    nargs="?", help="Path to curriculum .txt file")
    parser.add_argument("--model", type=str, help="Skip model selection")
    parser.add_argument("--lang",  type=str, default=None, help="Output language code")
    parser.add_argument("--mode",  type=str, choices=MODES, default=None,
                        help="plan = study plan only | full = plan + material, one pass, fast | "
                             "book = plan + chained per-topic chapters, slow but resumable "
                             "(default: ask)")
    parser.add_argument("--skip-assessment", action="store_true",
                        help="skip the learner familiarity assessment")
    parser.add_argument("--fresh", action="store_true",
                        help="book mode: discard any in-progress partial run and start over")
    return parser.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    input_path = Path(args.file if args.file else ask_file())
    if not input_path.exists():
        print(f"[error] file not found: {input_path}")
        exit(1)

    raw = input_path.read_text(encoding="utf-8").strip()

    # model selection
    if args.model:
        model = args.model
    else:
        models = list_models()
        if not models:
            print("[error] no matching models found. check MODEL_KEYWORDS.")
            exit(1)
        model = ask_model(models)

    # language selection
    lang = args.lang if args.lang in LANG_INSTRUCTION else None
    if lang is None:
        lang = ask_language()

    # mode selection
    mode = args.mode if args.mode in MODES else ask_mode()

    # cache check
    if find_cached(str(input_path), model, lang, mode):
        print("[done]")
        exit(0)

    # book mode — check for a resumable in-progress run
    resumed = False
    partial_state = None
    p_path = None
    if mode == "book":
        p_path = partial_path(str(input_path), model, lang)
        if args.fresh and p_path.exists():
            print("[book] --fresh: discarding previous in-progress run")
        loaded = None if args.fresh else load_partial(p_path)
        if loaded and loaded.get("source") == os.path.basename(str(input_path)):
            n_done  = len(loaded["completed"])
            n_total = len(loaded["material_topics"])
            if n_done >= n_total:
                print(f"[book] found a completed partial run ({n_done}/{n_total}) "
                      f"that wasn't cleaned up — starting fresh")
            elif ask_resume(n_done, n_total):
                partial_state = loaded
                resumed = True
            else:
                print("[book] starting fresh — previous progress will be overwritten")

    if resumed:
        frontmatter         = partial_state["frontmatter"]
        assessment_summary  = partial_state["assessment_summary"]
        plan_body           = partial_state["plan_body"]
        material_topics     = partial_state["material_topics"]
        print(frontmatter)
    else:
        # call 1 — frontmatter (fast, no stream)
        frontmatter, topics = generate_frontmatter(raw, model, mode)
        print(frontmatter)

        # assessment — gauge learner's current proficiency
        if args.skip_assessment:
            print("\n[assessment] skipped (--skip-assessment)")
            assessment_summary = ""
        else:
            assessment_summary = run_assessment(raw, topics, model)

        # call 2 — study plan (streaming)
        plan_body = generate_plan(raw, lang, model, assessment_summary)

    sections = []
    if assessment_summary:
        sections.append(("Learner Assessment", assessment_summary))
    sections.append(("Study Plan", plan_body))

    # call 2b — expand topic list from plan (fast, no stream)
    # call 3   — study material (streaming, only if full/book mode)
    if mode == "full":
        expanded = extract_topics_from_plan(plan_body, model)
        material_topics = expanded if expanded else topics
        material_body = generate_material(raw, material_topics, lang, model, assessment_summary)
        sections.append(("Study Material", material_body))
    elif mode == "book":
        if not resumed:
            expanded = extract_topics_from_plan(plan_body, model)
            material_topics = expanded if expanded else topics
            partial_state = {
                "source": os.path.basename(str(input_path)),
                "model": model,
                "lang": lang,
                "frontmatter": frontmatter,
                "assessment_summary": assessment_summary,
                "plan_body": plan_body,
                "material_topics": material_topics,
                "completed": [],
            }
            save_partial(p_path, partial_state)
        material_body = generate_book_material(
            raw, material_topics, lang, model, assessment_summary, partial_state, p_path,
        )
        sections.append(("Study Material", material_body))
        delete_partial(p_path)

    eject_model(model)
    save_output(frontmatter, sections, str(input_path), model, lang, mode)
    print("\n[done]")