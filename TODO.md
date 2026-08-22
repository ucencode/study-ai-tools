# TODO

What is left. Read [CLAUDE.md](CLAUDE.md) first — the invariants and the design stance
decide most of how these should be done.

Nothing here is a bug being ignored. Each one is a known edge with a cost that has so far
been smaller than the machinery to remove it, which is the bar anything below has to clear.

## Open

| Gap | Where it stands | What closing it looks like |
|---|---|---|
| **Retrying a slide job restarts OCR from page one** | Only after a crash *mid*-OCR. A run that finished is reused through the content-hash cache, so the ordinary retry is already cheap. | Checkpoint per page — `raw.txt` is already appended page by page, so the resume point is the line count, not new state. |
| **A crashed chapter leaves an orphaned `chapters/NN.md`** | Ignored on resume, because `job.json` is the authority. It is litter, not corruption. | Drop chapter files past `len(job.chapters)` when a run resumes. |
| **The single-worker requirement is documented, not enforced** | `--workers 2` silently creates two queues feeding one GPU, and nothing says so. | Refuse to start, or warn loudly, when more than one worker is configured. |
| **The model list goes stale as Ollama ships models** | Not fixable in code; `config/models.toml` is yours and gitignored, with `config/model_default.toml` as the checked-in starting point. | Nothing. Add entries as you pull models — `ollama show` reports capabilities, so roles do not have to be guessed. |

## Not planned

**Cancel.** `delete` refuses a live job on purpose rather than pulling files out from under
the worker. Cancelling safely means a cooperative checkpoint in every stage; the jobs are
minutes long and the queue is one deep, so waiting is cheaper than the machinery.

**Frontend tests.** A runner would spend the four-dependency budget the UI is built to.
Its behaviour was verified with throwaway Playwright scripts instead.

## History

The frontend brief that produced `frontend/` — visual language, layout, screen-by-screen
copy, and the acceptance list, all of it delivered — was this file up to commit `2ebfe23`.
Its load-bearing rules now live in CLAUDE.md's *The frontend* section; the rest is in
`git show 2ebfe23:TODO.md` if the reasoning behind a screen is ever worth re-reading.
