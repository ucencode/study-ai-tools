"""Curriculum → plan → textbook.

Full mode makes exactly one model call per chapter. The raw curriculum is never resent:
the `outline` stage distills it once into a scope note and a dependency list per chapter,
and each chapter closes with a machine-read ledger of what it established. Chapters that
declare no dependency are told to stand alone rather than left to invent a link.
"""

import math
import re
from pathlib import Path

from app.core import llm
from app.core.languages import LANG_INSTRUCTION
from app.core.markdown import normalize
from app.core.prompts import curriculum_generator as prompts
from app.models._job import now
from app.models.curriculum_generator import (
    Answer,
    ChapterState,
    CurriculumGeneratorJob,
    CurriculumGeneratorParams,
    CurriculumGeneratorResult,
    OutlineEntry,
    Question,
)
from app.repositories._job import new_id
from app.repositories.curriculum_generator import CurriculumGeneratorRepository

INPUT_FILE = "input.txt"
PLAN_FILE = "plan.md"
OUTPUT_FILE = "output.md"
CHAPTERS_DIR = "chapters"

MODES = [
    {"value": "short", "label": "Short Textbook",
     "description": "Condensed material across every topic in one pass, plus further references."},
    {"value": "full", "label": "Full Textbook",
     "description": "One full chapter per topic, chained through their real dependencies. "
                    "Slow, but checkpointed after every chapter — safe to interrupt."},
]


class CurriculumGeneratorService:
    def __init__(self, repository: CurriculumGeneratorRepository | None = None):
        self.repository = repository or CurriculumGeneratorRepository()

    # ── queries ──────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> CurriculumGeneratorJob | None:
        return self.repository.select_by_id(job_id)

    def select_all(self) -> list[CurriculumGeneratorJob]:
        return self.repository.select_all()

    def delete(self, job_id: str) -> None:
        self.repository.delete(job_id)

    def output(self, job_id: str) -> str:
        """The finished document, or the plan while the material is still being written."""
        if self.repository.select_by_id(job_id) is None:
            raise FileNotFoundError(f"no such job: {job_id}")
        for name in (OUTPUT_FILE, PLAN_FILE):
            path = self.repository.resolve(job_id, name)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    # ── the quiz, which needs a human in the middle ──────────────────────────

    async def build_quiz(self, curriculum: str, model: str) -> dict:
        """Familiarity questions to calibrate depth. Answers come back as job params."""
        metadata = await self._metadata(curriculum, model)
        topics = metadata.topics
        count = max(1, math.ceil(1 + 3.3 * math.log10(len(topics)))) if len(topics) > 1 else 1

        raw = await llm.complete_json(
            model=model,
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
            messages=[
                {"role": "system", "content": prompts.ASSESS_SYSTEM},
                {"role": "user", "content": prompts.ASSESS_USER.format(
                    raw=curriculum, topics=", ".join(topics), num_q=count)},
            ],
        )

        questions = [Question.model_validate(q) for q in raw[:count]]
        return {"questions": questions, "topics": topics, "metadata": metadata}

    # ── creation ─────────────────────────────────────────────────────────────

    def create(self, params: CurriculumGeneratorParams, curriculum: str) -> CurriculumGeneratorJob:
        job_id = new_id()
        job_dir = self.repository.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / INPUT_FILE).write_text(curriculum.strip(), encoding="utf-8")

        return self.repository.create(
            CurriculumGeneratorJob(id=job_id, input_path=INPUT_FILE, params=params)
        )

    # ── the pipeline ─────────────────────────────────────────────────────────

    async def run(self, job_id: str) -> CurriculumGeneratorJob:
        job = self.repository.require(job_id)
        self.repository.set_status(job_id, "processing")
        params = job.params
        curriculum = self.repository.resolve(job_id, INPUT_FILE).read_text(encoding="utf-8")

        try:
            job = await self._ensure_metadata(job_id, curriculum, params)
            plan = await self._ensure_plan(job_id, curriculum, params, job.result)
            job = await self._ensure_outline(job_id, plan, params)

            assessment = self._assessment_summary(params.questions, params.answers)

            if params.mode == "short":
                material = await self._short_material(job_id, params, job, assessment)
            else:
                material = await self._full_material(job_id, params, job, assessment)

            self._assemble(job_id, params, job.result, plan, material)

            job = self.repository.require(job_id)
            job.output_path = OUTPUT_FILE
            job.status = "completed"
            job.error = None
            job.finished_at = now()
            job.progress = None
            return self.repository.update(job)

        except Exception as e:
            return self.repository.set_status(job_id, "failed", f"{type(e).__name__}: {e}")
        finally:
            await llm.unload(params.model)

    # ── stages, each skippable when a previous run already did it ────────────

    async def _ensure_metadata(
        self, job_id: str, curriculum: str, params: CurriculumGeneratorParams
    ) -> CurriculumGeneratorJob:
        job = self.repository.require(job_id)
        if job.result is not None:
            return job

        self.repository.set_progress(job_id, "metadata", 0, 1)
        job = self.repository.require(job_id)
        job.result = await self._metadata(curriculum, params.model)
        return self.repository.update(job)

    async def _metadata(self, curriculum: str, model: str) -> CurriculumGeneratorResult:
        raw = await llm.complete_json(
            model=model,
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
            messages=[
                {"role": "system", "content": prompts.META_SYSTEM},
                {"role": "user", "content": prompts.META_USER.format(raw=curriculum)},
            ],
        )
        # The model is told the exact shape but still improvises keys; keep what fits.
        known = set(CurriculumGeneratorResult.model_fields)
        return CurriculumGeneratorResult.model_validate(
            {k: v for k, v in raw.items() if k in known}
        )

    async def _ensure_plan(
        self,
        job_id: str,
        curriculum: str,
        params: CurriculumGeneratorParams,
        result: CurriculumGeneratorResult | None,
    ) -> str:
        """The plan is always written — it is what the outline is derived from."""
        path = self.repository.resolve(job_id, PLAN_FILE)
        if path.exists():
            return path.read_text(encoding="utf-8")

        self.repository.set_progress(job_id, "plan", 0, 1)
        lang_name = LANG_INSTRUCTION[params.lang]
        user = prompts.PLAN_USER.format(lang_name=lang_name, raw=curriculum)
        if summary := self._assessment_summary(params.questions, params.answers):
            user += f"\n\n---\nLearner Assessment (use this to calibrate depth and focus):\n{summary}"

        return await self._stream_to_file(
            path,
            model=params.model,
            system=prompts.PLAN_SYSTEM,
            user=user,
            options={"temperature": 0.4, "num_ctx": 32768, "num_predict": 65536},
        )

    async def _ensure_outline(
        self, job_id: str, plan: str, params: CurriculumGeneratorParams
    ) -> CurriculumGeneratorJob:
        """One call that makes every later call cheap: scope + dependencies per chapter."""
        job = self.repository.require(job_id)
        if job.outline:
            return job

        self.repository.set_progress(job_id, "outline", 0, 1)
        raw = await llm.complete_json(
            model=params.model,
            options={"temperature": 0, "num_ctx": 32768, "num_predict": 8192},
            messages=[
                {"role": "system", "content": prompts.OUTLINE_SYSTEM},
                {"role": "user", "content": prompts.OUTLINE_USER.format(plan=plan)},
            ],
        )

        entries = [OutlineEntry.model_validate(e) for e in raw if e.get("topic")]
        if not entries:
            # The plan is unusable as an outline — fall back to the metadata topics.
            entries = [OutlineEntry(topic=t) for t in (job.result.topics if job.result else [])]

        job = self.repository.require(job_id)
        job.outline = self._prune_dependencies(entries)
        return self.repository.update(job)

    @staticmethod
    def _prune_dependencies(entries: list[OutlineEntry]) -> list[OutlineEntry]:
        """Keep only backward references to topics that actually exist.

        Models happily cite a later chapter or a topic they invented; either would send a
        chapter looking for context that will never arrive.
        """
        seen: set[str] = set()
        for entry in entries:
            entry.depends_on = [d for d in entry.depends_on if d in seen]
            seen.add(entry.topic)
        return entries

    # ── short mode ───────────────────────────────────────────────────────────

    async def _short_material(
        self,
        job_id: str,
        params: CurriculumGeneratorParams,
        job: CurriculumGeneratorJob,
        assessment: str,
    ) -> str:
        topics = [entry.topic for entry in job.outline]
        course = job.result.course if job.result else params.source_name
        lang_name = LANG_INSTRUCTION[params.lang]
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))

        self.repository.set_progress(job_id, "material", 0, 2)
        material = await self._stream_to_file(
            self.repository.resolve(job_id, "material.md"),
            model=params.model,
            system=prompts.MATERIAL_SYSTEM + self._topic_context_block(params, topics),
            user=prompts.MATERIAL_USER.format(
                lang_name=lang_name, topics=numbered, course=course,
                assessment=f"\n{assessment}\n" if assessment else "",
            ),
            options={"temperature": 0.3, "num_ctx": 65536, "num_predict": 131072},
        )

        self.repository.set_progress(job_id, "references", 1, 2)
        references = await self._stream_to_file(
            self.repository.resolve(job_id, "references.md"),
            model=params.model,
            system=prompts.REFERENCES_SYSTEM,
            user=prompts.REFERENCES_USER.format(
                lang_name=lang_name, course=course, topics=numbered),
            options={"temperature": 0.3, "num_ctx": 16384, "num_predict": 16384},
        )

        self.repository.set_progress(job_id, "references", 2, 2)
        return f"{material}\n\n{references}"

    def _topic_context_block(self, params: CurriculumGeneratorParams, topics: list[str]) -> str:
        relevant = {t: c for t, c in params.topic_context.items() if t in topics}
        if not relevant:
            return ""
        lines = "\n".join(f"- {topic}: {context}" for topic, context in relevant.items())
        return prompts.TOPIC_CONTEXT.format(context=lines)

    # ── full mode: one call per chapter ──────────────────────────────────────

    async def _full_material(
        self,
        job_id: str,
        params: CurriculumGeneratorParams,
        job: CurriculumGeneratorJob,
        assessment: str,
    ) -> str:
        outline = job.outline
        total = len(outline)
        chapters_dir = self.repository.job_dir(job_id) / CHAPTERS_DIR
        chapters_dir.mkdir(parents=True, exist_ok=True)

        # Byte-identical across every chapter of this job, so Ollama's prefix cache
        # covers it from chapter 2 onward. Never put varying text above this.
        stable = prompts.MATERIAL_TOPIC_STABLE.format(
            lang_name=LANG_INSTRUCTION[params.lang],
            total=total,
            course=job.result.course if job.result else params.source_name,
            assessment=f"{assessment}\n" if assessment else "",
            topic_sequence="\n".join(f"{i + 1}. {e.topic}" for i, e in enumerate(outline)),
        )

        done = {chapter.topic: chapter for chapter in job.chapters}
        established: dict[str, list[str]] = {t: c.established for t, c in done.items()}

        for index, entry in enumerate(outline, start=1):
            self.repository.set_progress(job_id, "chapters", index - 1, total)

            if entry.topic in done:
                continue  # a previous run already wrote it — this is the whole resume story

            body, terms = await self._chapter(
                path=chapters_dir / f"{index:02d}.md",
                model=params.model,
                stable=stable,
                entry=entry,
                index=index,
                total=total,
                context=params.topic_context.get(entry.topic, ""),
                established=established,
            )
            established[entry.topic] = terms

            job = self.repository.require(job_id)
            job.chapters.append(ChapterState(
                topic=entry.topic,
                file=f"{CHAPTERS_DIR}/{index:02d}.md",
                established=terms,
            ))
            self.repository.update(job)
            done[entry.topic] = job.chapters[-1]

        self.repository.set_progress(job_id, "chapters", total, total)

        job = self.repository.require(job_id)
        order = {chapter.topic: chapter for chapter in job.chapters}
        bodies = [
            self.repository.resolve(job_id, order[entry.topic].file).read_text(encoding="utf-8")
            for entry in outline if entry.topic in order
        ]
        return "\n\n".join(bodies)

    async def _chapter(
        self,
        *,
        path: Path,
        model: str,
        stable: str,
        entry: OutlineEntry,
        index: int,
        total: int,
        context: str,
        established: dict[str, list[str]],
    ) -> tuple[str, list[str]]:
        """Write one chapter and read back the terms it established."""
        if entry.depends_on:
            dependencies = "\n".join(
                f"- {topic}" + (f" — established: {'; '.join(established[topic])}"
                                if established.get(topic) else "")
                for topic in entry.depends_on
            )
            building_on = prompts.BUILDING_ON_SOME.format(dependencies=dependencies)
        else:
            building_on = prompts.BUILDING_ON_NONE

        task = prompts.MATERIAL_TOPIC_TASK.format(
            index=index,
            total=total,
            topic=entry.topic,
            scope=entry.scope or entry.topic,
            topic_context=prompts.TOPIC_CONTEXT.format(context=context) if context else "",
            building_on=building_on,
        )

        raw = await self._stream_to_file(
            path,
            model=model,
            system=prompts.MATERIAL_TOPIC_SYSTEM,
            user=stable + task,
            options={"temperature": 0.3, "num_ctx": 32768, "num_predict": 16384},
        )

        body, terms = self._split_ledger(raw, entry.topic)
        path.write_text(body, encoding="utf-8")  # rewrite without the marker line
        return body, terms

    @staticmethod
    def _split_ledger(text: str, topic: str) -> tuple[str, list[str]]:
        """Pull the trailing `<!-- established: ... -->` line off a chapter.

        When a model forgets the line, fall back to the chapter's own name. Every
        heading in the template is boilerplate, so there is nothing else in the body
        that says what this chapter fixed — a thin ledger beats a dead pipeline.
        """
        match = re.search(r"<!--\s*established:(.*?)-->", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            body = (text[: match.start()] + text[match.end():]).strip()
            terms = [t.strip() for t in match.group(1).split(";") if t.strip()]
            return body, terms or [topic]
        return text.strip(), [topic]

    # ── assembly ─────────────────────────────────────────────────────────────

    def _assemble(
        self,
        job_id: str,
        params: CurriculumGeneratorParams,
        result: CurriculumGeneratorResult | None,
        plan: str,
        material: str,
    ) -> None:
        frontmatter = {
            **(result.model_dump() if result else {}),
            "source": params.source_name,
            "lang": params.lang,
            "mode": params.mode,
            "model": params.model,
            "generated_on": now(),
        }

        sections: list[tuple[str, str]] = []
        if summary := self._assessment_summary(params.questions, params.answers):
            sections.append(("Learner Assessment", summary))
        if params.include_plan:
            sections.append(("Study Plan", plan))
        sections.append(("Study Material", material))

        body = "\n\n---\n\n".join(f"# {label}\n\n{content}" for label, content in sections)
        self.repository.resolve(job_id, OUTPUT_FILE).write_text(
            dict_to_yaml(frontmatter) + "\n" + body, encoding="utf-8"
        )

    @staticmethod
    def _assessment_summary(questions: list[Question], answers: list[Answer]) -> str:
        if not questions:
            return ""
        known_ids = {a.id for a in answers if a.known}
        known = [q for q in questions if q.id in known_ids]
        unknown = [q for q in questions if q.id not in known_ids]

        lines = [f"Learner familiarity: {len(known)}/{len(questions)} topics already known."]
        if known:
            lines.append("Already familiar with:")
            lines += [f"  - [{q.topic}] {q.question}" for q in known]
        if unknown:
            lines.append("Not yet familiar with:")
            lines += [f"  - [{q.topic}] {q.question}" for q in unknown]
        return "\n".join(lines)

    # ── shared ───────────────────────────────────────────────────────────────

    async def _stream_to_file(
        self, path: Path, *, model: str, system: str, user: str, options: dict
    ) -> str:
        """Stream a completion straight to disk so a poller sees it grow."""
        chunks: list[str] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as out:
            stream = llm.stream_chat(
                model=model,
                options=options,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            async for chunk in stream:
                chunks.append(chunk)
                out.write(chunk)
                out.flush()

        # Delimiters can straddle a chunk boundary, so the swap happens once at the end.
        # A poller sees the raw form until then; the saved file is always the fixed one.
        text = normalize("".join(chunks))
        path.write_text(text, encoding="utf-8")
        return text


def dict_to_yaml(data: dict) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines += [f'  - "{item}"' for item in value]
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f'{key}: "{str(value).replace(chr(34), chr(92) + chr(34))}"')
    lines.append("---")
    return "\n".join(lines) + "\n"
