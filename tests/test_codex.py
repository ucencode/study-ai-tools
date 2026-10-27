"""Codex as a text model: the CLI call, the settings that offer it, and where it may run."""

import asyncio
import json
from pathlib import Path

import pytest

from app.core import catalogue, codex, llm
from app.models.settings import CodexSettings, Settings
from app.services.settings import SettingsService
from test_slides import submit

# Taken before the autouse fixture stubs it, for the one test that exercises it.
REAL_USAGE = codex.usage


class FakeProcess:
    def __init__(self, returncode, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdin = None

    async def communicate(self, data=None):
        self.stdin = data
        return b"", self.stderr


@pytest.fixture
def codex_cli(monkeypatch):
    """Stands in for `codex exec`: records the call and writes the reply file."""
    calls = []
    state = {"returncode": 0, "reply": "The reply."}

    async def fake_exec(*args, **kwargs):
        process = FakeProcess(state["returncode"], b"usage limit reached")
        calls.append({"args": list(args), "process": process})
        if state["returncode"] == 0:
            Path(args[args.index("--output-last-message") + 1]).write_text(state["reply"])
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls, state


MESSAGES = [
    {"role": "system", "content": "You write study notes."},
    {"role": "user", "content": "Transactions."},
]


def test_a_codex_name_runs_one_ephemeral_read_only_turn(codex_cli):
    calls, _ = codex_cli

    reply = asyncio.run(llm.complete(model="codex/gpt-5.6-sol", messages=MESSAGES))

    assert reply == "The reply."
    args = calls[0]["args"]
    assert args[:2] == ["codex", "exec"]
    assert args[args.index("--model") + 1] == "gpt-5.6-sol"  # prefix stripped
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args  # no session is left in ~/.codex/sessions
    assert args[-1] == "-"  # prompt on stdin
    assert calls[0]["process"].stdin == b"You write study notes.\n\nTransactions."


def test_streaming_a_codex_model_yields_the_whole_reply_once(codex_cli):
    async def collect():
        return [chunk async for chunk in llm.stream_chat(model="codex/gpt-5.6-sol", messages=MESSAGES)]

    assert asyncio.run(collect()) == ["The reply."]


def test_a_failed_codex_run_is_an_llm_error_carrying_stderr(codex_cli):
    _, state = codex_cli
    state["returncode"] = 1

    with pytest.raises(llm.LLMError, match="usage limit reached"):
        asyncio.run(llm.complete(model="codex/gpt-5.6-sol", messages=MESSAGES))


def test_codex_refuses_images(codex_cli):
    calls, _ = codex_cli

    with pytest.raises(llm.LLMError, match="text-only"):
        asyncio.run(llm.complete(
            model="codex/gpt-5.6-sol", messages=[llm.image_message("Read this.", [b"png"])],
        ))
    assert calls == []


CATALOGUE = {"models": [
    {"slug": "gpt-6-luna", "visibility": "list"},
    {"slug": "gpt-5.6-terra", "visibility": "list"},
    {"slug": "codex-auto-review", "visibility": "hide"},
]}


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """The settings endpoint reads the login live; no test may run the real CLI for it."""
    async def fake_status():
        return "Logged in using ChatGPT"

    async def fake_usage():
        return {"plan": "free", "windows": [], "limit_reached": None, "lifetime_tokens": 0}

    monkeypatch.setattr(codex, "login_status", fake_status)
    monkeypatch.setattr(codex, "usage", fake_usage)


@pytest.fixture
def account_models(monkeypatch):
    """The account's model list, without running the CLI."""
    async def fake_list():
        return ["gpt-6-luna", "gpt-5.6-terra"]

    monkeypatch.setattr(codex, "list_models", fake_list)


def test_the_model_list_is_what_the_account_may_pick(monkeypatch):
    class Listing(FakeProcess):
        async def communicate(self, data=None):
            return json.dumps(CATALOGUE).encode(), b""

    async def fake_exec(*args, **kwargs):
        assert list(args) == ["codex", "debug", "models"]
        return Listing(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    # Hidden entries are internal agents, not choices.
    assert asyncio.run(codex.list_models()) == ["gpt-6-luna", "gpt-5.6-terra"]


def test_nothing_is_offered_until_switched_on(account_models):
    service = SettingsService()
    assert service.get().codex.enabled is False
    assert asyncio.run(service.codex_models()) == []

    service.update(Settings(codex=CodexSettings(enabled=True)))

    assert service.get().codex.enabled is True
    assert asyncio.run(service.codex_models()) == ["codex/gpt-6-luna", "codex/gpt-5.6-terra"]


def test_enabled_codex_models_are_offered_for_text_roles_only(fake_llm):
    names = ["codex/gpt-5.6-sol"]

    assert "codex/gpt-5.6-sol" in asyncio.run(catalogue.for_role("refine", names))
    assert "codex/gpt-5.6-sol" in asyncio.run(catalogue.for_role("llm", names))
    assert "codex/gpt-5.6-sol" not in asyncio.run(catalogue.for_role("vision", names))


def test_the_models_endpoint_follows_the_switch(client, fake_llm, account_models):
    assert "codex/gpt-6-luna" not in client.get("/api/models").json()["llm"]

    client.put("/api/settings", json={"codex": {"enabled": True}})

    models = client.get("/api/models").json()
    assert "codex/gpt-6-luna" in models["llm"]
    assert "codex/gpt-6-luna" in models["refine"]
    assert "codex/gpt-6-luna" not in models["vision"]


def test_a_failing_model_list_hides_codex_but_keeps_ollama(client, fake_llm, monkeypatch):
    async def broken():
        raise codex.CodexError("the codex CLI is not installed")

    monkeypatch.setattr(codex, "list_models", broken)
    client.put("/api/settings", json={"codex": {"enabled": True}})

    models = client.get("/api/models")
    assert models.status_code == 200
    names = [model["name"] for model in models.json()["models"]]
    assert set(fake_llm.installed) <= set(names)
    assert not any(llm.is_codex(name) for name in names)
    assert client.get("/api/settings").json()["codex_models_error"] == "the codex CLI is not installed"


def test_slides_accept_codex_for_summary_and_deep_only(client, fake_llm, pdf):
    deck = pdf(pages=1)

    rejected = submit(client, deck, action="clean", refine_model="codex/gpt-5.6-sol")
    assert rejected.status_code == 422
    assert "summary and deep" in rejected.json()["detail"]

    for action in ("summary", "deep"):
        accepted = submit(client, deck, action=action, refine_model="codex/gpt-5.6-sol")
        assert accepted.status_code == 202


class FakeAppServer:
    """Answers `initialize`, `account/rateLimits/read` and `account/usage/read` by id."""

    ANSWERS = {
        "initialize": {},
        "account/rateLimits/read": {"rateLimits": {
            "planType": "free",
            "primary": {"usedPercent": 5, "windowDurationMins": 43200, "resetsAt": 1795577358},
            "secondary": None,
            "rateLimitReachedType": None,
        }},
        "account/usage/read": {"summary": {"lifetimeTokens": 1234}},
    }

    def __init__(self):
        self.returncode = None
        self.lines = asyncio.Queue()
        self.stdin, self.stdout = self, self

    def write(self, data):
        message = json.loads(data)
        if "id" in message:
            # A notification first, as the real server sends them unasked.
            self.lines.put_nowait(json.dumps({"method": "account/updated"}).encode())
            answer = {"id": message["id"], "result": self.ANSWERS[message["method"]]}
            self.lines.put_nowait(json.dumps(answer).encode())

    async def drain(self):
        return None

    async def readline(self):
        return await self.lines.get()

    def terminate(self):
        self.returncode = -15

    async def wait(self):
        return self.returncode


def test_usage_is_read_from_the_app_server_without_a_model_call(monkeypatch):
    async def fake_exec(*args, **kwargs):
        assert list(args) == ["codex", "app-server"]
        return FakeAppServer()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    assert asyncio.run(REAL_USAGE()) == {
        "plan": "free",
        "windows": [{"used_percent": 5, "window_minutes": 43200, "resets_at": 1795577358}],
        "limit_reached": None,
        "lifetime_tokens": 1234,
    }
