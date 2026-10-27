"""The OpenAI Codex CLI as a text model, billed to the ChatGPT plan it is signed in with.

Each call is one fresh, ephemeral `codex exec` turn in an empty temporary directory with
a read-only sandbox, so no session is saved under ~/.codex/sessions and nothing on disk
is reachable. The reply arrives whole: Codex is used for text only, never for OCR.
"""

import asyncio
import json
import tempfile
from pathlib import Path


class CodexError(RuntimeError):
    """Anything that went wrong running the Codex CLI."""


async def run(model: str, messages: list[dict]) -> str:
    """One non-interactive turn. `model` is the Codex name, without the `codex/` prefix."""
    if any(m.get("images") for m in messages):
        raise CodexError(f"'{model}' is text-only; Codex models cannot do OCR")
    # Codex takes one prompt, so the system and user messages are sent in order.
    prompt = "\n\n".join(m["content"] for m in messages)

    with tempfile.TemporaryDirectory() as workdir:
        reply = Path(workdir) / "reply.md"
        try:
            process = await asyncio.create_subprocess_exec(
                "codex", "exec",
                "--model", model,
                "--sandbox", "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--cd", workdir,
                "--output-last-message", str(reply),
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise CodexError("the codex CLI is not installed") from e

        _, stderr = await process.communicate(prompt.encode())
        if process.returncode != 0:
            tail = stderr.decode(errors="replace").strip()[-2000:]
            raise CodexError(f"codex exited with {process.returncode}\n{tail}")
        return reply.read_text(encoding="utf-8") if reply.exists() else ""


async def login_status() -> str | None:
    """What `codex login status` prints, or None when the CLI is not installed."""
    try:
        process = await asyncio.create_subprocess_exec(
            "codex", "login", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return None
    output, _ = await process.communicate()
    return output.decode(errors="replace").strip()


async def usage() -> dict:
    """The account's plan, limit windows and token total, read without a model call.

    Asked of `codex app-server` over stdio (JSON-RPC, one message per line), which is how
    Codex's own `/status` gets them. Each window is how much of the plan's allowance is
    used and when it resets; `secondary` is absent on plans with a single window.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "codex", "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise CodexError("the codex CLI is not installed") from e

    async def send(message: dict) -> None:
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()

    async def reply(id: int) -> dict:
        while line := await process.stdout.readline():
            message = json.loads(line)
            if message.get("id") != id:
                continue  # a notification
            if "error" in message:
                raise CodexError(f"codex app-server: {message['error'].get('message')}")
            return message["result"]
        raise CodexError("codex app-server closed before answering")

    async def ask() -> tuple[dict, dict]:
        await send({"id": 1, "method": "initialize",
                    "params": {"clientInfo": {"name": "study-ai-tools", "version": "1.0.0"}}})
        await reply(1)
        await send({"method": "initialized"})
        await send({"id": 2, "method": "account/rateLimits/read"})
        limits = await reply(2)
        await send({"id": 3, "method": "account/usage/read"})
        return limits, await reply(3)

    try:
        limits, tokens = await asyncio.wait_for(ask(), timeout=20)
    except TimeoutError as e:
        raise CodexError("codex app-server did not answer within 20 seconds") from e
    except (ValueError, KeyError, TypeError) as e:
        raise CodexError(f"unexpected output from codex app-server: {e}") from e
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()

    rate = limits.get("rateLimits") or {}
    windows = [
        {
            "used_percent": window["usedPercent"],
            "window_minutes": window.get("windowDurationMins"),
            "resets_at": window.get("resetsAt"),
        }
        for window in (rate.get("primary"), rate.get("secondary"))
        if window
    ]
    return {
        "plan": rate.get("planType"),
        "windows": windows,
        "limit_reached": rate.get("rateLimitReachedType"),
        "lifetime_tokens": (tokens.get("summary") or {}).get("lifetimeTokens"),
    }


async def list_models() -> list[str]:
    """The models the signed-in account may use, as Codex's own model picker lists them.

    Read from `codex debug models`, the account's catalogue. Entries marked hidden are
    internal (review agents, reserves) and are left out.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "codex", "debug", "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise CodexError("the codex CLI is not installed") from e

    output, stderr = await process.communicate()
    if process.returncode != 0:
        raise CodexError(f"codex debug models exited with {process.returncode}\n"
                         f"{stderr.decode(errors='replace').strip()[-2000:]}")
    try:
        entries = json.loads(output)["models"]
        return [entry["slug"] for entry in entries if entry.get("visibility") == "list"]
    except (ValueError, KeyError, TypeError) as e:
        raise CodexError(f"unexpected output from codex debug models: {e}") from e
