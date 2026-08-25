import logging
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import ValidationError

from app.core.paths import PRESETS_DIR
from app.models._job import Strict
from app.models.preset import Preset

logger = logging.getLogger(__name__)

SettingsT = TypeVar("SettingsT", bound=Strict)


class PresetRepository(Generic[SettingsT]):
    """One file per preset, one directory per service: data/presets/{service}/{id}.json.

    Persistence only. Slugs, overwriting and the merge rule live in PresetService, which
    is the layer both the API and the CLI call.
    """

    def __init__(self, service: str, settings_model: type[SettingsT]):
        self.service = service
        self.model = Preset[settings_model]
        self.directory = PRESETS_DIR / service
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, id: str) -> Path:
        return self.directory / f"{id}.json"

    def select_all(self) -> list[Preset[SettingsT]]:
        presets = []
        for path in self.directory.glob("*.json"):
            try:
                presets.append(self.model.model_validate_json(path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                continue  # deleted between the glob and the read
            except ValidationError as e:
                # One preset written against an older field set must not break the whole
                # list — but silence would make it simply vanish.
                logger.warning("skipping unreadable preset %s: %s", path, e)
        return sorted(presets, key=lambda preset: preset.name.lower())

    def select_by_id(self, id: str) -> Preset[SettingsT] | None:
        path = self._path(id)
        if not path.exists():
            return None
        return self.model.model_validate_json(path.read_text(encoding="utf-8"))

    def create_or_replace(self, preset: Preset[SettingsT]) -> Preset[SettingsT]:
        path = self._path(preset.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(preset.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(path)
        return preset

    def delete(self, id: str) -> None:
        self._path(id).unlink(missing_ok=True)
