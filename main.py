"""study-ai-tools API.

    uv run fastapi dev

Serves frontend/dist at / when it has been built; `npm run dev` is only for iterating
on the UI.

Generation is job-based: a POST queues the run and returns an id, one background worker
executes queued jobs FIFO, and clients poll the job for status and output. Closing the
tab abandons the view, not the run.

The queue lives in this process, so run a *single* worker. `--reload` restarting mid-run
marks the in-flight job failed.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import worker
from app.routers import curriculum_generator, meta, slide_summarizer


@asynccontextmanager
async def lifespan(_: FastAPI):
    await worker.startup()
    try:
        yield
    finally:
        await worker.shutdown()


app = FastAPI(title="study-ai-tools", version="1.0.0", lifespan=lifespan)

# Only needed when running the Vite dev server against this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(slide_summarizer.router)
app.include_router(curriculum_generator.router)

# The built UI, when there is one: `cd frontend && npm run build`, and the whole app is
# this one process. Mounted last so /api keeps precedence, and guarded because dist/ is
# gitignored — a fresh clone has no build, and that must not stop the API from starting.
DIST_DIR = Path(__file__).parent / "frontend" / "dist"
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
