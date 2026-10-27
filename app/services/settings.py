from app.core import codex, llm
from app.models.settings import Settings
from app.repositories.settings import SettingsRepository


class SettingsService:
    def __init__(self, repository: SettingsRepository | None = None):
        self.repository = repository or SettingsRepository()

    def get(self) -> Settings:
        return self.repository.select() or Settings()

    def update(self, settings: Settings) -> Settings:
        return self.repository.save(settings)

    async def codex_models(self) -> list[str]:
        """The Codex models to offer, as `codex/<model>` names. Empty while disabled.

        Raises `codex.CodexError` when the CLI cannot list them.
        """
        if not self.get().codex.enabled:
            return []
        return [llm.CODEX_PREFIX + name for name in await codex.list_models()]
