#!/usr/bin/env python3
"""Curriculum → Self-Study Plan / Full Material.

The generation logic lives in `core.study_plan`; this file is the terminal
front-end for it — prompts, flags, and printing the stream as it arrives. The
web UI drives exactly the same generator.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import events as ev            # noqa: E402
from core import llm, storage            # noqa: E402
from core.languages import LANG_EXPERIMENTAL, LANG_INSTRUCTION  # noqa: E402
from core.paths import INPUT_DIR         # noqa: E402
from core.study_plan import (            # noqa: E402
    MODES,
    build_assessment,
    extract_metadata,
    generate,
    list_models,
    summarize_assessment,
)

RULE = "-" * 56


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
    print(f"\nOutput language? ({' / '.join(LANG_INSTRUCTION)}) [default: auto]")
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
        print("\nCurriculum file? (found in inputs/):")
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


def ask_resume(done: int, total: int) -> bool:
    print(f"\n[book] found an in-progress run: {done}/{total} chapters already written.")
    print("Resume from where it left off? [Y/n] (n = discard it and start over)")
    return (input(">>> ").strip().lower() or "y").startswith("y")


async def run_assessment(raw: str, topics: list[str], model: str) -> str:
    """Ask the familiarity questions in the terminal and fold in the answers."""
    print(f"\n[assessment] generating questions for {len(topics)} topics...", end=" ", flush=True)
    questions = await build_assessment(raw, topics, model)
    if not questions:
        print("failed — skipping assessment")
        return ""
    print(f"done ({len(questions)} questions)")

    print(f"\n[assessment] answer Y/N for each\n")
    known_ids = []
    for q in questions:
        while True:
            answer = input(f"  {q['question']} (Y/N): ").strip().upper()
            if answer in ("Y", "N", "YES", "NO"):
                break
            print("  Please answer Y or N.")
        if answer.startswith("Y"):
            known_ids.append(q["id"])

    print(f"\n[assessment] familiar with {len(known_ids)}/{len(questions)} topics")
    return summarize_assessment(questions, known_ids)


# ── stream printing ───────────────────────────────────────────────────────────

async def consume(stream) -> int:
    """Print a pipeline stream the way the old CLI did. Returns an exit code."""
    streaming = False
    async for event in stream:
        if event.type == ev.TOKEN:
            print(event.data["text"], end="", flush=True)
            streaming = True
            continue

        if streaming:  # close the streamed block before printing a status line
            print(f"\n{RULE}")
            streaming = False

        if event.type == ev.STATUS:
            stage = event.data.get("stage") or "info"
            print(f"[{stage}] {event.data['message']}")
        elif event.type == ev.SECTION:
            print(f"\n=== {event.data['label']} ===")
            print(RULE)
        elif event.type == ev.META and event.data.get("frontmatter"):
            print(event.data["frontmatter"])
        # DONE needs no line of its own — the pipeline reports every saved file as a status
        elif event.type == ev.ERROR:
            print(f"\n[error] {event.data['message']}", file=sys.stderr)
            return 1

    if streaming:
        print(f"\n{RULE}")
    return 0


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

async def main() -> int:
    args = parse_args()

    input_path = Path(args.file if args.file else ask_file())
    if not input_path.exists():
        print(f"[error] file not found: {input_path}", file=sys.stderr)
        return 1
    raw = input_path.read_text(encoding="utf-8").strip()

    if args.model:
        model = args.model
    else:
        try:
            models = await list_models()
        except llm.LLMError as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        if not models:
            print("[error] no matching models found. check MODEL_KEYWORDS.", file=sys.stderr)
            return 1
        model = ask_model(models)

    lang = args.lang if args.lang in LANG_INSTRUCTION else ask_language()
    mode = args.mode if args.mode in MODES else ask_mode()

    # book mode — offer to pick up an interrupted run before spending any tokens
    fresh = args.fresh
    resuming = False
    if mode == "book" and not fresh:
        partial = storage.peek_partial(input_path.name, model, lang)
        if partial:
            resuming = ask_resume(partial["completed"], partial["total"])
            fresh = not resuming
            if fresh:
                print("[book] starting fresh — previous progress will be overwritten")

    # the assessment is interactive, so it runs here rather than inside the pipeline
    assessment_summary = ""
    metadata = None
    if args.skip_assessment:
        print("\n[assessment] skipped (--skip-assessment)")
    elif resuming:
        print("\n[assessment] reusing the answers saved with the interrupted run")
    else:
        try:
            print("\n[meta] extracting curriculum metadata...", end=" ", flush=True)
            frontmatter, topics, _ = await extract_metadata(raw, model, mode)
            metadata = (frontmatter, topics)  # hand it to the pipeline; don't pay twice
            print(f"done ({len(topics)} topics)")  # the pipeline echoes the frontmatter
            assessment_summary = await run_assessment(raw, topics, model)
        except llm.LLMError as e:
            print(f"\n[error] {e}", file=sys.stderr)
            return 1

    code = await consume(generate(
        raw=raw,
        source_name=input_path.name,
        model=model,
        lang=lang,
        mode=mode,
        assessment_summary=assessment_summary,
        fresh=fresh,
        metadata=metadata,
    ))
    if code == 0:
        print("\n[done]")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[interrupted] book-mode progress is saved — rerun to resume.")
        raise SystemExit(130)
