#!/usr/bin/env python3

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

PRESET_DIR = Path(__file__).parent / "presets"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch process all PDF files in the project root using index.py"
    )
    parser.add_argument(
        "--preset",
        type=str,
        metavar="FILE",
        help="Preset file to use (from presets/<FILE>), passed to each index.py call. "
             "If omitted, you'll be prompted to pick one.",
    )
    return parser.parse_args()


def describe_preset(config: dict) -> str:
    mode = config.get("action", "?")
    ocr = config.get("vision_model", "?")
    refine = config.get("refine_model", "-") if mode != "skip" else "-"
    lang = config.get("lang", "?")
    level = config.get("level", "?")
    return f"mode:[{mode}] | OCR:[{ocr}] | refine:[{refine}] | lang:[{lang}] | level:[{level}]"


def run_preset_generator() -> str | None:
    before = set(PRESET_DIR.glob("*.toml")) if PRESET_DIR.exists() else set()

    generator_script = Path(__file__).parent / "preset-generator.py"
    result = subprocess.run([sys.executable, str(generator_script)])
    if result.returncode != 0:
        print(f"[error] preset-generator.py exited with code {result.returncode}")
        sys.exit(result.returncode)

    after = set(PRESET_DIR.glob("*.toml")) if PRESET_DIR.exists() else set()
    new_files = after - before
    if len(new_files) == 1:
        return new_files.pop().name
    return None


def ask_preset(new_name: str | None = None) -> str:
    presets = sorted(PRESET_DIR.glob("*.toml")) if PRESET_DIR.exists() else []

    print("Which preset do you want to use? (or type 'new' to create one)\n")
    entries = []
    for path in presets:
        try:
            with open(path, "rb") as f:
                config = tomllib.load(f)
            entries.append((path, describe_preset(config)))
        except Exception as e:
            entries.append((path, f"[unreadable: {e}]"))

    for i, (path, summary) in enumerate(entries, 1):
        label = f"[NEW!]{path.name}" if path.name == new_name else path.name
        print(f"  {i}. {label}")
        print(f"     {summary}")

    choice = input("\n>>> ").strip()

    if choice.lower() == "new":
        created = run_preset_generator()
        return ask_preset(new_name=created)

    if not entries:
        print(f"[error] no presets found in {PRESET_DIR}")
        sys.exit(1)

    try:
        return entries[int(choice) - 1][0].name
    except (ValueError, IndexError):
        print(f"[error] invalid choice: {choice!r}")
        sys.exit(1)


def main():
    args = parse_args()
    preset = args.preset or ask_preset()

    project_root = Path(__file__).parent.parent.parent.resolve()
    main_script = Path(__file__).parent / "index.py"

    pdfs = sorted((project_root / "inputs").glob("*.pdf"))

    if not pdfs:
        print("No PDF files found in inputs/.")
        sys.exit(1)

    total = len(pdfs)
    print(f"Found {total} PDF file(s). Starting batch processing with preset: {preset}\n")

    succeeded = []
    failed = []

    for i, pdf in enumerate(pdfs, start=1):
        print(f"[{i}/{total}] Processing: {pdf.name}")
        print("-" * 60)

        result = subprocess.run(
            [sys.executable, str(main_script), str(pdf), "--preset", preset]
        )

        if result.returncode == 0:
            succeeded.append(pdf.name)
            print(f"[{i}/{total}] Done: {pdf.name}\n")
        else:
            failed.append(pdf.name)
            print(f"[{i}/{total}] Failed (exit code {result.returncode}): {pdf.name}\n")

    print("=" * 60)
    print(f"Batch complete: {len(succeeded)}/{total} succeeded, {len(failed)}/{total} failed.")

    if succeeded:
        print("\nSucceeded:")
        for name in succeeded:
            print(f"  [ok] {name}")

    if failed:
        print("\nFailed:")
        for name in failed:
            print(f"  [!!] {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
