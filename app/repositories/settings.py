from pathlib import Path

from app.core.paths import SETTINGS_FILE
from app.models.settings import Settings


class SettingsRepository:
    """One file, data/settings.json. Persistence only; defaults live in SettingsService."""

    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path

    def select(self) -> Settings | None:
        """The stored settings, or None when nothing has been saved yet."""
        if not self.path.exists():
            return None
        return Settings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: Settings) -> Settings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Written beside and renamed over, so a crash mid-write never leaves half a file.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return settings
