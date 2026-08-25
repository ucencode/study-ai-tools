from typing import Generic, TypeVar

from pydantic import Field

from app.models._job import Strict, now

SettingsT = TypeVar("SettingsT", bound=Strict)


class Preset(Strict, Generic[SettingsT]):
    """A named set of run settings. Never the input — a preset that carried a document
    would resubmit the wrong file the next time it was applied."""

    # The slug of `name`, and the filename. `name` is kept as typed, for display.
    id: str
    name: str
    settings: SettingsT
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
