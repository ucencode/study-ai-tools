"""Which models get offered for which role, and which file that comes from."""

import asyncio

import pytest

from app.core import catalogue

LISTED = """
[[models]]
name = "qwen2.5vl:7b"
roles = ["vision"]
where = "local"

[[models]]
name = "gpt-oss:20b"
roles = ["refine", "llm"]
where = "local"

[[models]]
name = "gpt-oss:120b-cloud"
roles = ["refine", "llm"]
where = "cloud"
"""

DEFAULT = """
[[models]]
name = "gemma4:31b-cloud"
roles = ["vision", "refine", "llm"]
where = "cloud"
"""


@pytest.fixture
def catalogue_files(tmp_path, monkeypatch):
    """Point the catalogue at throwaway config files."""
    yours, default = tmp_path / "models.toml", tmp_path / "model_default.toml"
    default.write_text(DEFAULT)
    monkeypatch.setattr(catalogue, "MODELS_FILE", yours)
    monkeypatch.setattr(catalogue, "MODELS_DEFAULT_FILE", default)
    return yours, default


def test_only_explicitly_classified_models_are_offered(fake_llm, catalogue_files):
    """An unknown model is an unknown capability — offering a text model for OCR is
    worse than offering nothing."""
    yours, _ = catalogue_files
    yours.write_text(LISTED)

    assert asyncio.run(catalogue.for_role("vision")) == ["qwen2.5vl:7b"]
    assert asyncio.run(catalogue.for_role("llm")) == ["gpt-oss:120b-cloud", "gpt-oss:20b"]
    # gemma3:270m is installed but unclassified, so it is in neither list.
    assert "gemma3:270m" not in asyncio.run(catalogue.for_role("refine"))


def test_an_unlisted_model_is_still_returned_just_without_role_hints(fake_llm, catalogue_files):
    yours, _ = catalogue_files
    yours.write_text(LISTED)

    models = {model["name"]: model for model in asyncio.run(catalogue.available())}

    assert models["gemma3:270m"] == {
        "name": "gemma3:270m", "roles": [], "where": "local", "unlisted": True,
    }


def test_your_list_wins_over_the_checked_in_default(fake_llm, catalogue_files):
    yours, _ = catalogue_files
    yours.write_text(LISTED)

    assert asyncio.run(catalogue.for_role("vision")) == ["qwen2.5vl:7b"]


def test_the_default_is_used_when_you_have_not_written_one(fake_llm, catalogue_files):
    yours, _ = catalogue_files
    assert not yours.exists()

    assert asyncio.run(catalogue.for_role("llm")) == ["gemma4:31b-cloud"]


def test_creating_your_list_takes_effect_without_a_restart(fake_llm, catalogue_files):
    yours, _ = catalogue_files
    assert asyncio.run(catalogue.for_role("vision")) == ["gemma4:31b-cloud"]

    yours.write_text(LISTED)

    assert asyncio.run(catalogue.for_role("vision")) == ["qwen2.5vl:7b"]


def test_cloud_models_surface_even_when_ollama_has_not_pulled_them(fake_llm, catalogue_files):
    """They are reachable without ever appearing in `ollama list`."""
    yours, _ = catalogue_files
    yours.write_text(LISTED)
    assert "gpt-oss:120b-cloud" not in fake_llm.installed

    names = [model["name"] for model in asyncio.run(catalogue.available())]

    assert "gpt-oss:120b-cloud" in names


def test_a_local_model_you_have_not_pulled_is_not_offered(fake_llm, catalogue_files):
    yours, _ = catalogue_files
    yours.write_text(LISTED + '\n[[models]]\nname = "mistral:7b"\nroles = ["llm"]\nwhere = "local"\n')

    assert "mistral:7b" not in asyncio.run(catalogue.for_role("llm"))


def test_no_config_at_all_means_everything_is_unlisted(fake_llm, catalogue_files):
    yours, default = catalogue_files
    default.unlink()

    assert asyncio.run(catalogue.for_role("vision")) == []
    assert len(asyncio.run(catalogue.available())) == len(fake_llm.installed)
