# TODO

What is left. Read [CLAUDE.md](CLAUDE.md) first — the invariants and the design stance
decide most of how these should be done.

Nothing here is a bug being ignored. Each one is a known edge with a cost that has so far
been smaller than the machinery to remove it, which is the bar anything below has to clear.

## Open
### Add OpenAI API support for large-model generation

The application currently relies primarily on Ollama-compatible models. Larger or higher-quality models should also be usable through the OpenAI API without coupling curriculum or summarization logic directly to a specific provider.
The goal is to make model execution provider-agnostic so the application can choose between local Ollama models and remote OpenAI models depending on the configured role.

**Solution**
Introduce an LLM provider abstraction used by the service layer.
For example:

```text
Generation Service
        |
        v
   LLM Provider
    /       \
Ollama     OpenAI
```

Keep provider-specific authentication, request formatting, model names, and API behavior inside their respective provider implementations.
Job metadata should record the provider and model used where useful for debugging and reproducibility.

### Add downloadable generated artifacts

Large generated outputs such as curricula or textbooks are inconvenient to move through the clipboard.
Copying the complete output is still useful for small content, but it should not be the primary export mechanism for large generated documents.

**Solution**
Add a download action for completed job artifacts.
Prefer downloadable Markdown where the generated content is Markdown-compatible.

Potential actions:
```text
Download full result
Copy individual section
Copy chapter
Preview in application
```

The full generated document should not need to be copied into the clipboard just to save it elsewhere.

### Add partial progress reporting for Slide Summarizer
Slide Summarizer currently has processing stages that can take significantly different amounts of time depending on the number of pages and model speed.
A job can therefore appear to be processing without communicating how much work has actually completed.

**Solution**

Expose real progress from naturally measurable stages instead of using simulated percentages.

For example:
```text
Rendering pages       12 / 40
OCR                   10 / 40
OCR refinement         8 / 40
Generating summary
Completed
```
Store enough progress information in job metadata for the frontend to render intermediate progress consistently.
Where possible, progress should represent actual completed work rather than an estimated timer.

### Make job concurrency configurable

The job processor currently assumes limited concurrency. This should become explicitly configurable so the application can adapt to different hardware and remote-model environments.
Running multiple jobs concurrently can improve throughput, but excessive concurrency can contend for GPU memory, CPU, disk, Ollama execution capacity, cloud quotas, or provider rate limits.

**Solution**

Add a configurable concurrency limiter.
Possible initial configuration:

```text
MAX_CONCURRENT_JOBS=1
```

A default of **1** is the safest option and preserves predictable behavior on limited local hardware.
A default of **3** may provide better throughput where resources permit, but should only be chosen after testing resource contention.
Keep the value configurable regardless of the eventual default.
Longer term, consider separating job concurrency from LLM-call concurrency:

```text
MAX_CONCURRENT_JOBS=1
MAX_CONCURRENT_LLM_CALLS=3
```
This prevents several curriculum jobs from multiplying into an unexpectedly large number of simultaneous model requests.

### Enforce the single application-worker requirement
The application currently assumes a single application worker, but this requirement is only documented.
Starting the server with multiple workers can create independent queues that all feed the same underlying compute resources.

For example:
```text
Worker A -> Queue A --\
                       -> GPU / Ollama
Worker B -> Queue B --/
```

This bypasses the intended application-level concurrency limiter and can create resource contention or inconsistent queue behavior.

**Solution**

Explicitly reject unsupported multi-worker startup or emit a prominent warning.
Application worker count and job concurrency must remain separate concepts:

```text
1 application worker
        |
        v
Job scheduler
        |
        +-- Job A
        +-- Job B
        +-- Job C
```

Parallel job execution should be controlled by the application's concurrency limiter rather than by increasing server worker count.

### Resume Slide Summarizer OCR from completed pages

If a Slide Summarizer job crashes while OCR is still running, retrying the job currently restarts OCR from page one.
Completed OCR runs are already reused through the content-hash cache, so this issue only affects jobs interrupted during OCR.
For a large document, restarting from the beginning unnecessarily repeats completed work.

**Solution**

Checkpoint OCR progress per page.
`raw.txt` is already appended page by page, so existing output can potentially be used to determine the resume position without introducing additional persistent state.

For example:

```text
Pages 1-24 completed
Crash while processing page 25

Retry:
resume from page 25
```

The resume mechanism should verify that the existing OCR output is valid before relying on it.

### Keep Ollama model configuration manually extensible
The configured model list will naturally become outdated as new Ollama models are released or locally installed.
Automatically maintaining a complete list of all possible models is unnecessary because model availability differs between installations.
`config/models.toml` is local and gitignored, while `config/model_default.toml` acts as the checked-in starting configuration.

**Solution**
No automatic synchronization is required.
Users can add models to their local configuration as they install them.
Use information from `ollama show` where possible to determine model capabilities instead of guessing capabilities from model names.
The checked-in default configuration should remain a useful starting point rather than an exhaustive catalog of Ollama models.


## Not planned

### Cancel running jobs

The `delete` operation intentionally refuses to remove a live job.
Deleting files while a worker is actively processing them can leave the job in an inconsistent state. Safe cancellation would require cooperative cancellation checkpoints across every processing stage so each stage can stop cleanly before artifacts are removed.
Current jobs are generally short-lived and the queue depth is intentionally limited, so waiting for the active job to finish is currently cheaper and simpler than introducing cancellation machinery.

**Decision**
Do not implement job cancellation for now.
Revisit this if job duration, queue depth, or resource usage increases enough that waiting becomes materially inconvenient.

### Frontend automated tests

The frontend intentionally keeps its dependency footprint very small.
Adding a dedicated frontend test runner would increase the dependency and maintenance budget for a relatively small UI.
Current frontend behavior has instead been verified using temporary Playwright scripts during development.

**Decision**
Do not add a permanent frontend test framework for now.
Continue using lightweight manual or temporary browser automation where needed.
Revisit this if frontend complexity grows enough that regressions become difficult to verify reliably without persistent automated tests.

## History

The frontend brief that produced `frontend/` — visual language, layout, screen-by-screen
copy, and the acceptance list, all of it delivered — was this file up to commit `2ebfe23`.
Its load-bearing rules now live in CLAUDE.md's *The frontend* section; the rest is in
`git show 2ebfe23:TODO.md` if the reasoning behind a screen is ever worth re-reading.
