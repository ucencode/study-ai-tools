from app.models._job import Strict


class CodexSettings(Strict):
    # Off until switched on: Codex models are offered only when this is true. Which
    # models exist is read from the Codex CLI, never stored.
    enabled: bool = False


class Settings(Strict):
    """App-wide settings, stored in data/settings.json. Every field has a default, so a
    file written before a field existed still loads."""

    codex: CodexSettings = CodexSettings()
