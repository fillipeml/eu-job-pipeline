import json

import pytest

from eu_job_pipeline.models import Job, llm_output_schema
from eu_job_pipeline.scoring import (
    FixtureLLMClient,
    HeuristicScorer,
    LLMResult,
    LLMScorer,
    RecordingLLMClient,
    request_hash,
)

VALID = {
    "fit": 82,
    "verdict": "strong",
    "reasons": ["Skills overlap", "Visa offered"],
    "visa_sponsorship": "yes",
    "language_requirement": "english",
    "seniority": "mid",
    "workplace": "hybrid",
}


class FakeClient:
    model = "fake-model"

    def __init__(self, text, stop_reason="end_turn"):
        self.text = text
        self.stop_reason = stop_reason
        self.calls = 0

    def complete(self, system, user, schema):
        self.calls += 1
        return LLMResult(
            text=self.text,
            stop_reason=self.stop_reason,
            model=self.model,
            input_tokens=900,
            output_tokens=60,
            cache_read_tokens=800,
        )


@pytest.fixture
def job():
    return Job(
        source="t",
        external_id="1",
        title="AI Engineer",
        company="Acme",
        url="https://example.com",
        description="Python, LLM.",
    )


def test_valid_answer_becomes_a_record_with_usage(profile, job):
    rec = LLMScorer(FakeClient(json.dumps(VALID)), profile).score(job)
    assert rec.scorer == "llm:fake-model"
    assert rec.score.fit == 82 and rec.score.verdict == "strong"
    assert (rec.input_tokens, rec.output_tokens, rec.cache_read_tokens) == (900, 60, 800)


def test_out_of_range_fit_is_clamped(profile, job):
    rec = LLMScorer(FakeClient(json.dumps({**VALID, "fit": 150})), profile).score(job)
    assert rec.score.fit == 100


def test_malformed_answer_falls_back_to_heuristic(profile, job):
    fallback = HeuristicScorer(profile, ["DE"])
    rec = LLMScorer(FakeClient('{"fit": "high"}'), profile, fallback).score(job)
    assert rec is not None and rec.scorer == "heuristic"


def test_malformed_answer_without_fallback_is_none(profile, job):
    assert LLMScorer(FakeClient("not json"), profile).score(job) is None


def test_refusal_is_not_scored(profile, job):
    assert LLMScorer(FakeClient(None, stop_reason="refusal"), profile).score(job) is None


def test_fixture_roundtrip(tmp_path, profile, job):
    fallback = HeuristicScorer(profile, ["DE"])
    miss = LLMScorer(FixtureLLMClient(tmp_path, model="fake-model"), profile, fallback).score(job)
    assert miss.scorer == "heuristic"  # nothing recorded yet → fallback

    recorder = RecordingLLMClient(FakeClient(json.dumps(VALID)), tmp_path)
    recorded = LLMScorer(recorder, profile).score(job)
    assert recorded.scorer == "llm:fake-model"
    assert len(list(tmp_path.glob("*.json"))) == 1

    hit = LLMScorer(FixtureLLMClient(tmp_path, model="fake-model"), profile, fallback).score(job)
    assert hit.scorer == "llm:fake-model" and hit.score.fit == 82


def test_request_hash_is_stable_and_input_sensitive():
    a = request_hash("m", "sys", "user")
    assert a == request_hash("m", "sys", "user")
    assert a != request_hash("m", "sys", "other")
    assert a != request_hash("other", "sys", "user")


def test_output_schema_is_strict_and_flat():
    schema = llm_output_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    dumped = json.dumps(schema)
    for forbidden in ("minimum", "maximum", "minItems", "maxItems", "title", "$ref"):
        assert forbidden not in dumped
