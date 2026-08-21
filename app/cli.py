"""Run a pipeline straight from the terminal.

Calls the services directly — no HTTP, no worker, no queue. The job directory it leaves
behind is identical in shape to one the API produced.

    uv run python -m app.cli slides deck.pdf --action deep
    uv run python -m app.cli curriculum syllabus.txt --mode full --no-plan
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.core import catalogue, llm
from app.core.languages import LANG_EXPERIMENTAL, LANG_INSTRUCTION
from app.models.curriculum_generator import Answer, CurriculumGeneratorParams
from app.models.slide_summarizer import SlideSummarizerParams
from app.services.curriculum_generator import CurriculumGeneratorService
from app.services.slide_summarizer import SlideSummarizerService

ACTIONS = ("skip", "clean", "summary", "deep")
LEVELS = ("beginner", "intermediate", "advanced")
MODES = ("short", "full")


# ── prompts ──────────────────────────────────────────────────────────────────

def ask_choice(options: list[str], label: str) -> str:
    if not options:
        raise SystemExit(f"[error] no {label} available — is Ollama running?")
    print(f"\nSelect {label}:")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    print("[default: 1]")
    choice = input(">>> ").strip() or "1"
    try:
        return options[int(choice) - 1]
    except (ValueError, IndexError):
        print(f"[warn] invalid choice, using {options[0]}")
        return options[0]


def ask_language() -> str:
    print(f"\nOutput language? ({' / '.join(LANG_INSTRUCTION)}) [default: auto]")
    lang = input(">>> ").strip().lower() or "auto"
    if lang not in LANG_INSTRUCTION:
        print(f"[warn] unknown language '{lang}', using auto")
        return "auto"
    if lang in LANG_EXPERIMENTAL:
        print(f"[warn] '{LANG_INSTRUCTION[lang]}' quality depends on model proficiency.")
    return lang


def ask_enum(options: tuple[str, ...], label: str, default: str) -> str:
    print(f"\n{label}? ({' / '.join(options)}) [default: {default}]")
    choice = input(">>> ").strip().lower() or default
    if choice not in options:
        print(f"[warn] invalid choice, using {default}")
        return default
    return choice


def report(job, service) -> None:
    if job.status == "failed":
        print(f"\n[failed] {job.error}")
        raise SystemExit(1)
    path = service.repository.resolve(job.id, job.output_path)
    print(f"\n[done] {path}")


# ── slides ───────────────────────────────────────────────────────────────────

async def run_slides(args) -> None:
    source = Path(args.file)
    if not source.exists():
        raise SystemExit(f"[error] file not found: {source}")

    suffix = source.suffix.lower()
    if suffix not in (".pdf", ".pptx"):
        raise SystemExit(f"[error] expected a .pdf or .pptx file, got {suffix or 'no extension'}")

    ocr_model = args.ocr_model or ask_choice(await catalogue.for_role("vision"), "vision model")
    action = args.action or ask_enum(ACTIONS, "Refine mode", "skip")

    refine_model, lang, level = None, "auto", None
    if action != "skip":
        refine_model = args.refine_model or ask_choice(
            await catalogue.for_role("refine"), "refine model")
        lang = args.lang or ask_language()
        if action in ("summary", "deep"):
            level = args.level or ask_enum(LEVELS, "Audience level", "intermediate")

    service = SlideSummarizerService()
    job = service.create(
        SlideSummarizerParams(
            filename=source.name,
            source_format=suffix.lstrip("."),
            dpi=args.dpi,
            ocr_model=ocr_model,
            action=action,
            refine_model=refine_model,
            lang=lang,
            level=level,
        ),
        source,
    )

    print(f"[job] {job.id}  ({service.repository.job_dir(job.id)})")
    report(await service.run(job.id), service)


# ── curriculum ───────────────────────────────────────────────────────────────

async def run_curriculum(args) -> None:
    source = Path(args.file)
    if not source.exists():
        raise SystemExit(f"[error] file not found: {source}")
    curriculum = source.read_text(encoding="utf-8").strip()

    model = args.model or ask_choice(await catalogue.for_role("llm"), "model")
    lang = args.lang or ask_language()
    mode = args.mode or ask_enum(MODES, "Mode", "short")

    service = CurriculumGeneratorService()
    questions, answers = [], []

    if not args.skip_quiz:
        print("\n[quiz] generating familiarity questions...")
        try:
            quiz = await service.build_quiz(curriculum, model)
            questions = quiz["questions"]
            print(f"[quiz] {len(questions)} questions — answer Y/N for each\n")
            for question in questions:
                while (reply := input(f"  {question.question} (Y/N): ").strip().upper()) not in \
                        ("Y", "N", "YES", "NO"):
                    print("  Please answer Y or N.")
                answers.append(Answer(id=question.id, known=reply.startswith("Y")))
        except llm.LLMError as e:
            print(f"[quiz] skipped: {e}")

    job = service.create(
        CurriculumGeneratorParams(
            source_name=source.name,
            model=model,
            lang=lang,
            mode=mode,
            include_plan=not args.no_plan,
            questions=questions,
            answers=answers,
        ),
        curriculum,
    )

    print(f"\n[job] {job.id}  ({service.repository.job_dir(job.id)})")
    report(await service.run(job.id), service)


# ── args ─────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    slides = sub.add_parser("slides", help="PDF or PPTX → OCR → refined document")
    slides.add_argument("file")
    slides.add_argument("--dpi", type=int, default=200)
    slides.add_argument("--ocr-model")
    slides.add_argument("--action", choices=ACTIONS)
    slides.add_argument("--refine-model")
    slides.add_argument("--lang")
    slides.add_argument("--level", choices=LEVELS)
    slides.set_defaults(run=run_slides)

    curriculum = sub.add_parser("curriculum", help="curriculum → study plan + textbook")
    curriculum.add_argument("file")
    curriculum.add_argument("--model")
    curriculum.add_argument("--lang")
    curriculum.add_argument("--mode", choices=MODES)
    curriculum.add_argument("--no-plan", action="store_true",
                            help="generate the plan but keep it out of the document")
    curriculum.add_argument("--skip-quiz", action="store_true")
    curriculum.set_defaults(run=run_curriculum)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(args.run(args))
    except KeyboardInterrupt:
        print("\n[interrupted] progress is saved — rerun to resume")
        sys.exit(130)


if __name__ == "__main__":
    main()
