import re
from typing import Generic, TypeVar

from app.models._job import Strict, now
from app.models.curriculum_generator import SERVICE as CURRICULUM_SERVICE
from app.models.curriculum_generator import CurriculumGeneratorSettings
from app.models.preset import Preset
from app.models.slide_summarizer import SERVICE as SLIDES_SERVICE
from app.models.slide_summarizer import SlideSummarizerSettings
from app.repositories.preset import PresetRepository

SettingsT = TypeVar("SettingsT", bound=Strict)

MAX_NAME = 80

_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """The id, and the filename. Constrained to [a-z0-9-] so a name can never escape the
    preset directory — there is no traversal to guard against if none is representable."""
    slug = _NOT_SLUG.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("a preset name needs at least one letter or digit")
    if len(slug) > MAX_NAME:
        raise ValueError(f"a preset name is at most {MAX_NAME} characters")
    return slug


class PresetService(Generic[SettingsT]):
    def __init__(self, service: str, settings_model: type[SettingsT]):
        self.service = service
        self.settings_model = settings_model
        self.repository = PresetRepository(service, settings_model)

    def list(self) -> list[Preset[SettingsT]]:
        return self.repository.select_all()

    def get(self, id: str) -> Preset[SettingsT]:
        preset = self.repository.select_by_id(id)
        if preset is None:
            raise FileNotFoundError(f"no such preset: {id}")
        return preset

    def save(self, name: str, settings: SettingsT) -> Preset[SettingsT]:
        """Create, or overwrite the preset of the same name. Saving over is the way to
        edit a loadout, so there is no separate update."""
        id = slugify(name)
        existing = self.repository.select_by_id(id)
        return self.repository.create_or_replace(
            self.repository.model(
                id=id,
                name=name.strip(),
                settings=settings,
                created_at=existing.created_at if existing else now(),
                updated_at=now(),
            )
        )

    def delete(self, id: str) -> None:
        self.get(id)  # 404 before deleting, rather than a silent no-op
        self.repository.delete(id)

    def apply(self, id: str, **overrides) -> SettingsT:
        """The preset, then anything explicitly supplied on top.

        `None` means "not supplied", which is exactly what argparse leaves an unset flag
        as — so a CLI `--preset fast --lang id` is one call and no new logic. The result
        goes back through the settings model, so an override is bound-checked the same
        way a fresh submission is.
        """
        supplied = {key: value for key, value in overrides.items() if value is not None}
        return self.settings_model.model_validate(
            {**self.get(id).settings.model_dump(), **supplied}
        )


# Instantiated once and shared, the way the pipeline services are.
SLIDE_PRESETS: PresetService[SlideSummarizerSettings] = PresetService(
    SLIDES_SERVICE, SlideSummarizerSettings
)
CURRICULUM_PRESETS: PresetService[CurriculumGeneratorSettings] = PresetService(
    CURRICULUM_SERVICE, CurriculumGeneratorSettings
)
