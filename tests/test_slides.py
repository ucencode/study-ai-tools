"""The slide pipeline: convert → ocr → refine, and what the API does around it."""

from conftest import wait_for

SERVICE = "slide-summarizer"


def submit(client, path, **fields):
    form = {"ocr_model": "qwen2.5vl:7b", "action": "skip", **fields}
    with path.open("rb") as handle:
        return client.post(
            f"/api/{SERVICE}/jobs",
            files={"file": (path.name, handle, "application/pdf")},
            data=form,
        )


def test_pdf_runs_through_ocr_and_refine(client, fake_llm, progress_log, pdf):
    response = submit(client, pdf(pages=3), action="summary", refine_model="gpt-oss:20b")
    assert response.status_code == 202

    job = wait_for(client, SERVICE, response.json()["id"])
    assert job["status"] == "completed", job["error"]
    assert job["result"]["pages"] == 3
    assert job["result"]["ocr_cached"] is False
    assert job["result"]["output_chars"] > 0

    # A PDF skips `convert`; every page is counted; refine closes the run.
    assert [stage for stage, _, _ in progress_log] == [
        "ocr", "ocr", "ocr", "ocr", "refine", "refine",
    ]
    assert [(current, total) for _, current, total in progress_log] == [
        (0, 3), (1, 3), (2, 3), (3, 3), (0, 1), (1, 1),
    ]
    assert job["progress"] is None  # cleared when the job ends


def test_skip_stops_after_the_raw_transcript(client, fake_llm, progress_log, pdf):
    job = wait_for(client, SERVICE, submit(client, pdf(pages=2)).json()["id"])

    assert job["status"] == "completed"
    assert {stage for stage, _, _ in progress_log} == {"ocr"}
    assert job["output_path"] == "raw.txt"  # the transcript is the deliverable

    output = client.get(f"/api/{SERVICE}/jobs/{job['id']}/output").json()["content"]
    assert "Page 1 transcript." in output and "Refined text." not in output


def test_a_page_that_fails_ocr_does_not_kill_the_run(client, fake_llm, pdf):
    fake_llm.fail_pages = {2}

    job = wait_for(client, SERVICE, submit(client, pdf(pages=3)).json()["id"])

    assert job["status"] == "completed"
    output = client.get(f"/api/{SERVICE}/jobs/{job['id']}/output").json()["content"]
    assert "[missing page 2]" in output
    assert "Page 1 transcript." in output and "Page 3 transcript." in output


def test_ocr_cache_keys_on_content_not_filename(client, fake_llm, pdf):
    deck = pdf(pages=2, name="monday.pdf")

    first = wait_for(client, SERVICE, submit(client, deck).json()["id"])
    assert first["result"]["ocr_cached"] is False
    assert fake_llm.ocr_pages == 2

    # Same bytes under another name: the transcript is reused, not re-run.
    renamed = deck.with_name("tuesday.pdf")
    renamed.write_bytes(deck.read_bytes())
    second = wait_for(client, SERVICE, submit(client, renamed).json()["id"])
    assert second["result"]["ocr_cached"] is True
    assert fake_llm.ocr_pages == 2

    # A different lecture under the *same* name is a different lecture.
    other = pdf(pages=2, name="monday.pdf")
    third = wait_for(client, SERVICE, submit(client, other).json()["id"])
    assert third["result"]["ocr_cached"] is False
    assert fake_llm.ocr_pages == 4


def test_upload_must_be_pdf_or_pptx(client, fake_llm, tmp_path):
    note = tmp_path / "notes.txt"
    note.write_text("not a deck")

    response = submit(client, note)

    assert response.status_code == 400
    assert "pdf" in response.json()["detail"]


def test_a_live_job_refuses_delete_and_retry(client, fake_llm, pdf):
    """409 is the race the UI has to render as a race rather than an error."""
    from app.services.slide_summarizer import SlideSummarizerService

    job_id = wait_for(client, SERVICE, submit(client, pdf()).json()["id"])["id"]
    service = SlideSummarizerService()
    service.repository.set_status(job_id, "processing")

    assert client.delete(f"/api/{SERVICE}/jobs/{job_id}").status_code == 409
    assert client.post(f"/api/{SERVICE}/jobs/{job_id}/retry").status_code == 409

    service.repository.set_status(job_id, "failed", "done pretending")
    assert client.delete(f"/api/{SERVICE}/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/{SERVICE}/jobs/{job_id}").status_code == 404


def test_paths_stay_relative_to_the_job_directory(client, fake_llm, pdf):
    job = wait_for(
        client, SERVICE,
        submit(client, pdf(), action="clean", refine_model="gpt-oss:20b").json()["id"],
    )

    assert job["input_path"] == "input.pdf"
    assert job["output_path"] == "output.md"
