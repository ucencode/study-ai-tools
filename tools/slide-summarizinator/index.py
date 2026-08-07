#!/usr/bin/env python3
"""PDF OCR pipeline.

The OCR and refine stages live in `core.slides`; this file is the terminal
front-end — prompts, presets, and printing the stream as it arrives. The web UI
drives exactly the same generator.
"""

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import events as ev            # noqa: E402
from core import llm                     # noqa: E402
from core.languages import (             # noqa: E402
    AUDIENCE_INSTRUCTION,
    LANG_EXPERIMENTAL,
    LANG_INSTRUCTION,
)
from core.paths import PRESET_DIR        # noqa: E402
from core.slides import ACTIONS, generate, list_refine_models, list_vision_models  # noqa: E402

RULE = "-" * 56


# ── interactive prompts ───────────────────────────────────────────────────────

def ask_model(models: list[str], label: str = "model") -> str:
    print(f"\nSelect {label}:")
    for i, m in enumerate(models, 1):
        print(f"  {i}. {m}")
    print("[default: 1]")
    choice = input(">>> ").strip() or "1"
    try:
        return models[int(choice) - 1]
    except (ValueError, IndexError):
        print(f"[warn] invalid choice, using {models[0]}")
        return models[0]


def ask_action() -> str:
    print("""
Refine output? (
  1. skip - do nothing
  2. clean - fix OCR mess only
  3. summary - compress into notes
  4. deep - structured + analogy + understanding
) [default: skip]""")
    choice = input(">>> ").strip() or "1"
    return {"1": "skip", "2": "clean", "3": "summary", "4": "deep"}.get(choice, "skip")


def ask_language() -> str:
    print(f"\nLanguage for compiled output? ({' / '.join(LANG_INSTRUCTION)}) [default: auto]")
    lang = input(">>> ").strip().lower() or "auto"
    if lang not in LANG_INSTRUCTION:
        print(f"[warn] unknown language '{lang}', using auto")
        return "auto"
    if lang in LANG_EXPERIMENTAL:
        print(f"[warn] '{LANG_INSTRUCTION[lang]}' output quality depends on the refine model's "
              f"proficiency in this language. Results may vary.")
    return lang


def ask_audience() -> str:
    print("""
Audience level? (
  1. beginner - explain from scratch
  2. intermediate - some familiarity assumed
  3. advanced - skip basics, focus on nuance
) [default: 2]""")
    choice = input(">>> ").strip() or "2"
    return {"1": "beginner", "2": "intermediate", "3": "advanced"}.get(choice, "intermediate")


# ── presets ───────────────────────────────────────────────────────────────────

def load_preset(filename: str) -> dict:
    config_path = PRESET_DIR / filename
    if not config_path.exists():
        available = [f.name for f in PRESET_DIR.glob("*.toml")] if PRESET_DIR.exists() else []
        print(f"[error] preset not found: {config_path}", file=sys.stderr)
        if available:
            print(f"[hint] available presets: {', '.join(sorted(available))}", file=sys.stderr)
        sys.exit(1)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


async def check_preset(config: dict, filename: str) -> None:
    """Fail fast on a bad preset, before any page is rendered."""
    def fail(message: str):
        print(f"[error] {message}", file=sys.stderr)
        sys.exit(1)

    missing = {"vision_model", "action", "lang", "level"} - config.keys()
    if missing:
        fail(f"missing keys in {filename}: {', '.join(sorted(missing))}")
    if config["action"] not in ACTIONS:
        fail(f"invalid action '{config['action']}' in {filename}. "
             f"Must be one of: {', '.join(sorted(ACTIONS))}")
    if config["lang"] not in LANG_INSTRUCTION:
        fail(f"invalid lang '{config['lang']}' in {filename}. "
             f"Must be one of: {', '.join(LANG_INSTRUCTION)}")
    if config["level"] not in AUDIENCE_INSTRUCTION:
        fail(f"invalid level '{config['level']}' in {filename}. "
             f"Must be one of: {', '.join(AUDIENCE_INSTRUCTION)}")

    try:
        available = set(await llm.list_models())
    except llm.LLMError as e:
        fail(str(e))

    if config["vision_model"] not in available:
        fail(f"vision_model '{config['vision_model']}' not found in ollama. "
             f"Available: {', '.join(sorted(available))}")
    if config["action"] != "skip":
        if "refine_model" not in config:
            fail(f"missing key 'refine_model' in {filename} (required when action != skip)")
        if config["refine_model"] not in available:
            fail(f"refine_model '{config['refine_model']}' not found in ollama. "
                 f"Available: {', '.join(sorted(available))}")


# ── stream printing ───────────────────────────────────────────────────────────

async def consume(stream) -> int:
    streaming = False
    async for event in stream:
        if event.type == ev.TOKEN:
            print(event.data["text"], end="", flush=True)
            streaming = True
            continue

        if streaming:
            print(f"\n{RULE}")
            streaming = False

        if event.type == ev.STATUS:
            print(f"[{event.data.get('stage') or 'info'}] {event.data['message']}")
        elif event.type == ev.SECTION:
            print(f"\n=== {event.data['label']} ===")
            print(RULE)
        # DONE needs no line of its own — the pipeline reports every saved file as a status
        elif event.type == ev.ERROR:
            print(f"\n[error] {event.data['message']}", file=sys.stderr)
            return 1

    if streaming:
        print(f"\n{RULE}")
    return 0


# ── args ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="PDF OCR Pipeline")
    parser.add_argument("file", nargs="?", help="Path to PDF file")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI (default: 200)")
    parser.add_argument("--preset", type=str, metavar="FILE",
                        help="Load preset from presets/<FILE>, skip interactive prompts")
    return parser.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    args = parse_args()
    if not args.file:
        print("[usage] python index.py <file.pdf> [--preset <FILE>] [--dpi <N>]", file=sys.stderr)
        return 1

    pdf_path = Path(args.file)
    if not pdf_path.exists():
        print(f"[error] file not found: {args.file!r}", file=sys.stderr)
        return 1

    if args.preset:
        config = load_preset(args.preset)
        await check_preset(config, args.preset)

        ocr_model, action = config["vision_model"], config["action"]
        lang, level = config["lang"], config["level"]
        refine_model = config.get("refine_model")
        print(f"[config] vision_model={ocr_model} action={action} lang={lang} level={level}")
        if lang in LANG_EXPERIMENTAL:
            print(f"[warn] '{LANG_INSTRUCTION[lang]}' output quality depends on the refine "
                  f"model's proficiency in this language. Results may vary.")
    else:
        try:
            vision_models = await list_vision_models()
        except llm.LLMError as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        if not vision_models:
            print("[error] no vision models found. check OCR_MODEL_KEYWORDS.", file=sys.stderr)
            return 1
        ocr_model = ask_model(vision_models, label="vision model")

        action = ask_action()
        refine_model, lang, level = None, "auto", None
        if action != "skip":
            refine_models = await list_refine_models()
            if not refine_models:
                print("[error] no refine models found. check REFINE_MODEL_KEYWORDS.", file=sys.stderr)
                action = "skip"
            else:
                refine_model = ask_model(refine_models, label="refine model")
                lang = ask_language()
                level = ask_audience() if action in ("summary", "deep") else None

    code = await consume(generate(
        pdf_path=pdf_path,
        ocr_model=ocr_model,
        action=action,
        refine_model=refine_model,
        lang=lang,
        level=level,
        dpi=args.dpi,
    ))
    if code == 0:
        print("\n[done]")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
