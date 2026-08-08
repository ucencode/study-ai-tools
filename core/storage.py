"""Output files, frontmatter, result caching and resumable partial state."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from core.paths import SLIDES_OUTPUT_DIR, STUDY_PLAN_OUTPUT_DIR

STUDY_PLAN_SUFFIX = {"plan": "study_plan", "full": "full", "book": "book"}


# ── helpers ───────────────────────────────────────────────────────────────────

def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def slugify(value: str, limit: int = 40) -> str:
    return re.sub(r"[^\w]+", "_", value.lower()).strip("_")[:limit]


def dict_to_yaml(data: dict) -> str:
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
            lines.append(f'{key}: "{str(val).replace(chr(34), chr(92) + chr(34))}"')
    lines.append("---")
    return "\n".join(lines) + "\n"


def read_frontmatter(path: Path) -> dict:
    """Parse the leading `---` block of a generated file into a flat dict."""
    meta: dict[str, str] = {}
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


def strip_frontmatter(content: str) -> str:
    parts = content.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else content


# ── study plan output ─────────────────────────────────────────────────────────

def find_cached_plan(source_name: str, model: str, lang: str, mode: str) -> Path | None:
    """A previously generated plan for the same source/model/lang/mode, if any."""
    if not STUDY_PLAN_OUTPUT_DIR.exists():
        return None
    pattern = f"*-{STUDY_PLAN_SUFFIX[mode]}.md"
    for path in sorted(STUDY_PLAN_OUTPUT_DIR.glob(pattern), reverse=True):
        meta = read_frontmatter(path)
        if (meta.get("source") == source_name
                and meta.get("model") == model
                and meta.get("lang") == lang
                and meta.get("mode") == mode):
            return path
    return None


def save_plan(frontmatter: str, sections: list[tuple[str, str]], *,
              source_name: str, lang: str, mode: str) -> Path:
    STUDY_PLAN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = STUDY_PLAN_OUTPUT_DIR / f"{timestamp()}-{slugify(Path(source_name).stem)}-{STUDY_PLAN_SUFFIX[mode]}.md"

    fm = frontmatter.rstrip().removesuffix("---")
    fm += f'\nsource: "{source_name}"\n'
    fm += f'lang: "{lang}"\n'
    fm += "---\n"

    body = "\n\n---\n\n".join(f"# {label}\n\n{content}" for label, content in sections)
    path.write_text(fm + "\n" + body, encoding="utf-8")
    return path


# ── book-mode partial state (resume after Ctrl+C / a closed browser tab) ──────

def partial_path(source_name: str, model: str, lang: str) -> Path:
    return (STUDY_PLAN_OUTPUT_DIR / ".partial"
            / f"{slugify(Path(source_name).stem)}__{slugify(model, 60)}__{lang}.json")


def load_partial(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_partial(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def delete_partial(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def load_resumable_partial(path: Path, source_name: str) -> dict | None:
    """A saved book run for this source that still has chapters left to write."""
    state = load_partial(path)
    if not state or state.get("source") != source_name:
        return None
    if len(state.get("completed", [])) >= len(state.get("material_topics", [])):
        return None  # finished but never cleaned up — not resumable
    return state


def peek_partial(source_name: str, model: str, lang: str) -> dict | None:
    """Progress summary for a resumable book run, or None when there isn't one."""
    path = partial_path(source_name, model, lang)
    state = load_resumable_partial(path, source_name)
    if not state:
        return None
    return {"path": str(path),
            "completed": len(state["completed"]),
            "total": len(state["material_topics"])}


# ── slide pipeline output ─────────────────────────────────────────────────────

def find_cached_ocr(pdf_name: str, ocr_model: str) -> Path | None:
    """A raw OCR transcript for the same PDF basename and vision model."""
    if not SLIDES_OUTPUT_DIR.exists():
        return None
    for path in sorted(SLIDES_OUTPUT_DIR.glob("*-raw.txt"), reverse=True):
        meta = read_frontmatter(path)
        if meta.get("file") == pdf_name and meta.get("model") == ocr_model:
            return path
    return None


def load_raw_ocr(path: Path) -> str:
    return strip_frontmatter(path.read_text(encoding="utf-8"))


def save_raw_ocr(text: str, stamp: str, *, pdf_name: str, pages: int, dpi: int, model: str) -> Path:
    SLIDES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = SLIDES_OUTPUT_DIR / f"{stamp}-raw.txt"
    meta = dict_to_yaml({
        "file": pdf_name,
        "timestamp": stamp,
        "pages": pages,
        "dpi": dpi,
        "model": model,
    })
    path.write_text(meta + "\n" + text, encoding="utf-8")
    return path


def save_refined(text: str, stamp: str, *, origin: str, raw_file: str,
                 model: str, mode: str, lang: str, level: str | None) -> Path:
    SLIDES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = SLIDES_OUTPUT_DIR / f"{stamp}-compiled.txt"
    meta = dict_to_yaml({
        "origin": origin,
        "file": raw_file,
        "timestamp": stamp,
        "model": model,
        "mode": mode,
        "lang": lang,
        "level": {"beginner": 1, "intermediate": 2, "advanced": 3}.get(level, "n/a"),
    })
    path.write_text(meta + "\n" + text, encoding="utf-8")
    return path


# ── output browsing (used by the web UI) ──────────────────────────────────────

_OUTPUT_DIRS = {
    "slide-summarizinator": SLIDES_OUTPUT_DIR,
    "study-plan-generatinator": STUDY_PLAN_OUTPUT_DIR,
}


def list_outputs() -> list[dict]:
    """Every generated file, newest first, with its frontmatter attached."""
    entries = []
    for tool, directory in _OUTPUT_DIRS.items():
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            stat = path.stat()
            entries.append({
                "tool": tool,
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "meta": read_frontmatter(path),
            })
    return sorted(entries, key=lambda e: e["modified"], reverse=True)


def resolve_output(tool: str, name: str) -> Path:
    """Resolve a listed output to a real path, refusing anything outside it."""
    directory = _OUTPUT_DIRS.get(tool)
    if directory is None:
        raise FileNotFoundError(f"unknown tool: {tool}")
    path = (directory / name).resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise FileNotFoundError(f"no such output: {name}")
    return path


def format_duration(seconds: float) -> str:
    """Render a duration as e.g. '45s', '3m12s', '1h05m' for progress/ETA messages."""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def unique_input_path(filename: str) -> Path:
    """A collision-free path under inputs/ for an uploaded file."""
    from core.paths import INPUT_DIR

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = INPUT_DIR / f"{slugify(stem, 60) or 'upload'}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = INPUT_DIR / f"{slugify(stem, 60) or 'upload'}-{counter}{suffix}"
        counter += 1
    return candidate


__all__ = [name for name in dir() if not name.startswith("_")]
