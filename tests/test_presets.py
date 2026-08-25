"""Saved settings: the service rules the CLI will use, and the endpoints the UI uses."""

import json
import logging

import pytest
from pydantic import ValidationError

from app.core import paths
from app.models.curriculum_generator import CurriculumGeneratorSettings
from app.models.slide_summarizer import SlideSummarizerSettings
from app.services.preset import CURRICULUM_PRESETS, SLIDE_PRESETS

SLIDES_URL = "/api/slide-summarizer/presets"
CURRICULUM_URL = "/api/curriculum-generator/presets"


def slides(**fields):
    return SlideSummarizerSettings(**{"ocr_model": "vision:8b", **fields})


# ── the service, called directly — this is the surface the CLI gets ──────────────


def test_apply_returns_the_stored_settings_when_nothing_is_overridden():
    preset = SLIDE_PRESETS.save("Deep Indonesian", slides(action="deep", lang="id", dpi=300))

    assert SLIDE_PRESETS.apply(preset.id) == preset.settings


def test_an_explicit_option_beats_the_preset_and_none_means_not_supplied():
    preset = SLIDE_PRESETS.save("Deep Indonesian", slides(action="deep", lang="id", dpi=300))

    # An unset argparse flag is None, which must not wipe what the preset chose.
    assert SLIDE_PRESETS.apply(preset.id, lang=None).lang == "id"

    applied = SLIDE_PRESETS.apply(preset.id, lang="en")
    assert applied.lang == "en"
    assert (applied.action, applied.dpi) == ("deep", 300)


def test_an_override_is_bound_checked_like_a_fresh_submission():
    preset = SLIDE_PRESETS.save("Deep Indonesian", slides())

    with pytest.raises(ValidationError):
        SLIDE_PRESETS.apply(preset.id, dpi=9999)
    with pytest.raises(ValidationError):
        SLIDE_PRESETS.apply(preset.id, action="sideways")


def test_applying_or_deleting_an_unknown_preset_is_an_error_not_a_no_op():
    with pytest.raises(FileNotFoundError):
        SLIDE_PRESETS.apply("nope")
    with pytest.raises(FileNotFoundError):
        SLIDE_PRESETS.delete("nope")


def test_a_name_with_nothing_to_slug_is_refused_and_writes_nothing():
    with pytest.raises(ValueError):
        SLIDE_PRESETS.save("///", slides())

    assert SLIDE_PRESETS.list() == []


def test_saving_over_a_name_replaces_it_and_keeps_when_it_was_created():
    first = SLIDE_PRESETS.save("Fast local", slides(ocr_model="a:1"))
    second = SLIDE_PRESETS.save("fast  LOCAL", slides(ocr_model="b:2"))

    assert second.id == first.id
    assert second.created_at == first.created_at
    assert [preset.settings.ocr_model for preset in SLIDE_PRESETS.list()] == ["b:2"]


def test_the_two_services_do_not_share_a_namespace():
    SLIDE_PRESETS.save("Fast", slides())
    CURRICULUM_PRESETS.save("Fast", CurriculumGeneratorSettings(model="gpt-oss:20b"))

    assert SLIDE_PRESETS.apply("fast").ocr_model == "vision:8b"
    assert CURRICULUM_PRESETS.apply("fast").model == "gpt-oss:20b"


def test_a_preset_written_against_an_older_field_set_is_skipped_not_fatal(caplog):
    good = SLIDE_PRESETS.save("Keep me", slides())
    stale = paths.PRESETS_DIR / "slide_summarizer" / "stale.json"
    stale.write_text(json.dumps({"id": "stale", "name": "Stale", "settings": {"gone": 1}}))

    with caplog.at_level(logging.WARNING):
        assert [preset.id for preset in SLIDE_PRESETS.list()] == [good.id]
    assert "stale" in caplog.text


# ── the endpoints ────────────────────────────────────────────────────────────────


def test_a_preset_round_trips_through_the_api(client):
    body = {"name": "Deep Indonesian", "settings": slides(action="deep", lang="id").model_dump()}

    saved = client.post(SLIDES_URL, json=body).json()
    assert saved["id"] == "deep-indonesian"
    assert saved["settings"]["action"] == "deep"

    assert [preset["id"] for preset in client.get(SLIDES_URL).json()] == ["deep-indonesian"]

    assert client.delete(f"{SLIDES_URL}/deep-indonesian").status_code == 204
    assert client.get(SLIDES_URL).json() == []


def test_curriculum_presets_have_their_own_endpoints(client):
    body = {"name": "Full run", "settings": {"model": "gpt-oss:20b", "mode": "full"}}

    saved = client.post(CURRICULUM_URL, json=body).json()
    assert saved["settings"] == {
        "model": "gpt-oss:20b",
        "lang": "auto",
        "mode": "full",
        "include_plan": True,
    }
    assert [preset["id"] for preset in client.get(CURRICULUM_URL).json()] == ["full-run"]


def test_deleting_an_unknown_preset_is_a_404(client):
    assert client.delete(f"{SLIDES_URL}/nope").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Bad", "settings": {"ocr_model": "v:1", "dpi": 9999}},
        {"name": "Bad", "settings": {"model": "m", "mode": "sideways"}},
        # A preset holds settings, never the input.
        {"name": "Bad", "settings": {"ocr_model": "v:1", "filename": "lecture.pdf"}},
        {"name": "///", "settings": {"ocr_model": "v:1"}},
        {"name": "", "settings": {"ocr_model": "v:1"}},
    ],
)
def test_the_settings_model_rejects_at_the_boundary(client, body):
    assert client.post(SLIDES_URL, json=body).status_code == 422
    assert client.get(SLIDES_URL).json() == []


def test_a_job_submitted_after_the_params_split_still_reads_back(client, pdf, fake_llm):
    """The settings/params split is a re-parenting, so records keep round-tripping."""
    deck = pdf(pages=2, name="lecture.pdf")
    with deck.open("rb") as handle:
        response = client.post(
            "/api/slide-summarizer/jobs",
            files={"file": (deck.name, handle, "application/pdf")},
            data={"ocr_model": "vision:8b", "action": "skip", "dpi": "200"},
        )

    params = response.json()["params"]
    assert params["filename"] == "lecture.pdf"
    assert params["dpi"] == 200
    assert "preset" not in response.json()
