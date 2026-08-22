"""The endpoints the UI leans on before it can submit anything."""

from conftest import wait_for


def test_health_reports_ollama_up(client, fake_llm):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["ollama"] == "up"
    assert isinstance(body["libreoffice"], bool)


def test_health_reports_ollama_down_rather_than_failing(client, fake_llm):
    """A stopped Ollama is a normal state the UI renders in amber, not an error."""
    fake_llm.list_error = "could not reach Ollama — is it running?"

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ollama"] == "down"


def test_models_is_503_when_ollama_is_unreachable(client, fake_llm):
    fake_llm.list_error = "could not reach Ollama — is it running?"

    response = client.get("/api/models")

    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


def test_config_offers_every_choice_the_forms_need(client, fake_llm):
    body = client.get("/api/config").json()

    assert [action["value"] for action in body["actions"]] == ["skip", "clean", "summary", "deep"]
    assert [mode["value"] for mode in body["modes"]] == ["short", "full"]
    assert [level["value"] for level in body["audiences"]] == [
        "beginner", "intermediate", "advanced",
    ]
    assert body["languages"][0]["value"] == "auto"
    assert isinstance(body["pptx_enabled"], bool)


def test_jobs_merges_both_services_newest_first(client, fake_llm, pdf):
    deck = pdf(pages=1)
    with deck.open("rb") as handle:
        slides = client.post(
            "/api/slide-summarizer/jobs",
            files={"file": (deck.name, handle, "application/pdf")},
            data={"ocr_model": "qwen2.5vl:7b", "action": "skip"},
        ).json()
    wait_for(client, "slide-summarizer", slides["id"])

    curriculum = client.post(
        "/api/curriculum-generator/jobs",
        json={"curriculum": "A syllabus.", "model": "gpt-oss:20b"},
    ).json()
    wait_for(client, "curriculum-generator", curriculum["id"])

    jobs = client.get("/api/jobs").json()

    assert {job["service"] for job in jobs} == {"slide_summarizer", "curriculum_generator"}
    assert [job["created_at"] for job in jobs] == sorted(
        (job["created_at"] for job in jobs), reverse=True
    )


def test_jobs_can_be_filtered_to_one_service(client, fake_llm):
    client.post("/api/curriculum-generator/jobs",
                json={"curriculum": "A syllabus.", "model": "gpt-oss:20b"})

    jobs = client.get("/api/jobs?service_name=curriculum_generator").json()

    assert {job["service"] for job in jobs} == {"curriculum_generator"}


def test_an_unknown_service_is_404_not_an_empty_list(client, fake_llm):
    response = client.get("/api/jobs?service_name=slide-summarizer")

    assert response.status_code == 404
    assert "unknown service" in response.json()["detail"]


def test_a_missing_job_is_404(client, fake_llm):
    assert client.get("/api/slide-summarizer/jobs/nope").status_code == 404
    assert client.get("/api/curriculum-generator/jobs/nope/output").status_code == 404
