import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from careermatch.api import ROOT, app
from careermatch.chunking import chunk_document
from careermatch.extraction import extract_instructor, extract_rules, validate_extraction
from careermatch.matching import DemoEmbedding, match
from careermatch.models import MatchRequest, Requirement, Requirements


@pytest.fixture
def request_data():
    return MatchRequest.model_validate_json(
        (ROOT / "fixtures/demo.json").read_text(encoding="utf-8")
    )


def test_demo_ranking_and_provenance(request_data):
    result = match(request_data)
    assert result.matches[0].id == "backend-01"
    assert result.matches[-1].id == "ml-04"
    assert result.matches[0].coverage == 1
    search = next(m for m in result.matches if m.id == "search-02")
    assert search.gaps == ["kubernetes", "aws"]
    for job in result.matches:
        for excerpt in job.suggested_excerpts:
            assert request_data.resume[excerpt.start : excerpt.end] == excerpt.quote
        for req in job.requirements:
            raw = next(j for j in request_data.jobs if j.id == job.id)
            assert req.job_quote in raw.text


def test_chunk_boundaries_and_stable_ids():
    text = "# Skills\n  Python and APIs.  \n# Long project\n" + "asynchronous search " * 120
    chunks = chunk_document(text, 150, 30)
    assert len(chunks) > 10
    assert chunks[0].section == "Skills"
    assert chunks[1].section == "Long project"
    assert chunks == chunk_document(text, 150, 30)
    assert all(text[c.start : c.end] == c.text and len(c.text) <= 150 for c in chunks)
    coverage = set()
    for c in chunks[1:]:
        coverage.update(range(c.start, c.end))
    assert all(i in coverage for i in range(chunks[1].start, chunks[-1].end))


def test_whitespace_and_unicode_offsets_are_exact(request_data):
    source = "\n  # Work\n  Built Python APIs ☀ " + "a b  c   " * 180 + "\n  "
    request_data = MatchRequest(resume=source, jobs=request_data.jobs)
    assert request_data.resume == source
    chunks = chunk_document(source, 79, 23)
    assert all(source[c.start : c.end] == c.text for c in chunks)
    for job in match(request_data).matches:
        assert all(source[e.start : e.end] == e.quote for e in job.suggested_excerpts)


def test_negation_and_no_invented_skills(request_data):
    request_data.resume = "# Skills\nNo Python experience.\nLearning Kubernetes.\nI build ceramics."
    result = match(request_data)
    assert all(m.coverage == 0 and m.suggested_excerpts == [] for m in result.matches)


def test_machine_learning_is_not_a_learning_goal(request_data):
    skills = {r.skill for r in extract_rules(request_data.jobs[-1]).requirements}
    assert {"machine learning", "pytorch", "python", "aws", "kubernetes"} == skills


def test_isolation(request_data):
    first = match(request_data)
    request_data.resume = "Designing pottery and hand-painted ceramics for local exhibitions."
    assert all(not m.suggested_excerpts for m in match(request_data).matches)
    assert first.matches[0].coverage == 1


def test_empty_requirements_not_perfect_match(request_data):
    request_data.jobs[0].text = "Build wonderful things with empathy and communicate effectively."
    result = match(request_data)
    unknown = next(m for m in result.matches if m.id == "backend-01")
    assert unknown.rank_score == unknown.coverage == 0


@pytest.mark.parametrize(
    "quote,skill",
    [
        ("invented Python claim", "python"),
        ("Build Python APIs.", "kubernetes"),
        ("No Python experience.", "python"),
    ],
)
def test_reject_ungrounded_extraction(quote, skill):
    with pytest.raises(ValueError):
        validate_extraction(
            Requirements(requirements=[Requirement(skill=skill, quote=quote)]),
            "Build Python APIs. No Python experience.",
        )


def test_instructor_missing_configuration_is_clear(monkeypatch, request_data):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Set OPENAI_API_KEY"):
        extract_instructor(request_data.jobs[0])


def test_instructor_adapter_validates_provider_output(monkeypatch, request_data):
    from types import SimpleNamespace

    import instructor

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-placeholder")
    monkeypatch.setenv("CAREERMATCH_LLM_MODEL", "unit-test-model")
    job = request_data.jobs[0]
    quote = "Build Python services with FastAPI and PostgreSQL."
    output = Requirements(requirements=[Requirement(skill="python", quote=quote)])

    def create(**kwargs):
        assert kwargs["response_model"] is Requirements
        assert kwargs["messages"][-1]["content"] == job.text
        return output

    monkeypatch.setattr(
        instructor,
        "from_provider",
        lambda *a: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    assert extract_instructor(job).requirements[0].quote == quote
    output.requirements[0].quote = "Invented Python role"
    with pytest.raises(ValueError, match="source verification"):
        extract_instructor(job)


def test_duplicates_rejected(request_data):
    data = request_data.model_dump()
    data["jobs"].append(data["jobs"][0])
    with pytest.raises(ValidationError, match="unique"):
        MatchRequest.model_validate(data)


def test_embedding_deterministic():
    encoder = DemoEmbedding()
    assert encoder.encode(["Python API"]) == encoder.encode(["Python API"])
    assert len(encoder.encode(["Python"])[0]) == 384


def test_api_end_to_end_and_validation(request_data):
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["storage"] == "request-scoped-in-memory"
        assert client.get("/api/demo").json()["jobs"][0]["id"] == "backend-01"
        result = client.post("/api/match", json=request_data.model_dump())
        assert result.status_code == 200
        assert result.json()["matches"][0]["id"] == "backend-01"
        assert client.post("/api/match", json={"resume": "short", "jobs": []}).status_code == 422
        data = json.loads(request_data.model_dump_json())
        data["resume"] = "# " + "heading " * 10
        assert client.post("/api/match", json=data).status_code == 422
