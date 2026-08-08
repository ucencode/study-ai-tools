"""Filesystem layout shared by the CLIs and the web server."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_DIR   = PROJECT_ROOT / "inputs"
OUTPUT_ROOT = PROJECT_ROOT / "outputs"

SLIDES_OUTPUT_DIR     = OUTPUT_ROOT / "slide-summarizinator"
STUDY_PLAN_OUTPUT_DIR = OUTPUT_ROOT / "study-plan-generatinator"

# background job records + event logs; deliberately outside the two tool
# directories so list_outputs() never picks them up
JOBS_DIR = OUTPUT_ROOT / ".jobs"

PRESET_DIR   = PROJECT_ROOT / "tools" / "slide-summarizinator" / "presets"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
