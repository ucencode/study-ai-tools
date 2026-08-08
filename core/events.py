"""The event vocabulary every pipeline generator speaks.

A pipeline is more than one long string — it moves through stages, streams the
body of each one, and finishes by writing a file. Rather than yielding bare
text and losing that shape, generators yield :class:`StreamEvent` objects.
``token`` events carry the generated text chunks; the rest carry the progress
information the CLI used to ``print``.

``StreamEvent.to_sse()`` renders one event as a Server-Sent Events frame, which
is all the FastAPI layer needs to do to put a pipeline on the wire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Event types, in roughly the order a consumer sees them.
STATUS  = "status"    # progress line: {"stage": str, "message": str, ...}
SECTION = "section"   # a new output section starts: {"key": str, "label": str}
TOKEN   = "token"     # a chunk of generated text: {"text": str}
META    = "meta"      # structured payload (frontmatter, topic list, ...)
DONE    = "done"      # pipeline finished: {"path": str, ...}
ERROR   = "error"     # pipeline aborted: {"message": str}
JOB     = "job"       # job record snapshot: {"id": str, "status": str, ...}


@dataclass(slots=True)
class StreamEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Render as an SSE frame.

        The payload is JSON-encoded, which escapes newlines for us — a raw ``\\n``
        inside a ``data:`` line would otherwise terminate the frame early.
        """
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.type}\ndata: {payload}\n\n"


def status(message: str, stage: str = "", **extra: Any) -> StreamEvent:
    return StreamEvent(STATUS, {"stage": stage, "message": message, **extra})


def section(key: str, label: str, **extra: Any) -> StreamEvent:
    return StreamEvent(SECTION, {"key": key, "label": label, **extra})


def token(text: str, **extra: Any) -> StreamEvent:
    return StreamEvent(TOKEN, {"text": text, **extra})


def meta(**data: Any) -> StreamEvent:
    return StreamEvent(META, data)


def done(**data: Any) -> StreamEvent:
    return StreamEvent(DONE, data)


def error(message: str, **extra: Any) -> StreamEvent:
    return StreamEvent(ERROR, {"message": message, **extra})


def job(record: dict) -> StreamEvent:
    """A job record snapshot.

    Emitted by the job layer, never by a pipeline. Clients read `status` from it
    to know whether a run is queued, live, or finished — a terminal one is the
    last frame an attached client sees.
    """
    return StreamEvent(JOB, dict(record))
