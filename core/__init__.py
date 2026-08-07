"""Shared AI generation core for study-ai-tools.

Every pipeline in here is an ``async`` generator that yields :class:`StreamEvent`
objects as the model produces them, so the same code drives both the CLIs in
``tools/`` and the SSE endpoints in ``main.py``.
"""

from core.events import StreamEvent
from core.paths import INPUT_DIR, OUTPUT_ROOT, PROJECT_ROOT

__all__ = ["StreamEvent", "INPUT_DIR", "OUTPUT_ROOT", "PROJECT_ROOT"]
