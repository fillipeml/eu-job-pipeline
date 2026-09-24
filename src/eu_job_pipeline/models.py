"""Domain models shared by sources, store, scorers and reports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["strong", "possible", "weak"]
Visa = Literal["yes", "no", "unknown"]
Language = Literal["english", "german", "other", "unknown"]
Seniority = Literal["junior", "mid", "senior", "unknown"]
Workplace = Literal["remote", "hybrid", "onsite", "unknown"]


class Job(BaseModel):
    """A normalised job posting. `source` + `external_id` identify it across runs."""

    source: str
    external_id: str
    title: str
    company: str
    location: str = ""
    country: str | None = None  # ISO 3166-1 alpha-2, or "EU" for pan-European postings
    remote: bool | None = None
    url: str
    description: str = ""
    posted_at: date | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"

    def text(self) -> str:
        """Everything a scorer may look at, lower-cased."""
        return " ".join(
            [self.title, self.company, self.location, self.description, *self.tags]
        ).lower()


class JobScore(BaseModel):
    """What a scorer says about one job for one candidate.

    This is also the structured-output schema handed to the LLM, so it stays flat:
    only strings, integers, enums and lists of strings.
    """

    model_config = ConfigDict(extra="forbid")

    fit: int = Field(description="Fit for this candidate, 0 (no fit) to 100 (ideal)")
    verdict: Verdict
    reasons: list[str] = Field(description="Up to five short reasons, most important first")
    visa_sponsorship: Visa = Field(
        description="Does the posting offer visa sponsorship or relocation?"
    )
    language_requirement: Language = Field(description="Working language the posting requires")
    seniority: Seniority
    workplace: Workplace

    def clamped(self) -> JobScore:
        """Enforce the ranges the JSON schema cannot express."""
        fit = max(0, min(100, self.fit))
        return self.model_copy(update={"fit": fit, "reasons": self.reasons[:5]})


class ScoreRecord(BaseModel):
    """A `JobScore` plus provenance and cost, as stored."""

    job_key: str
    score: JobScore
    scorer: str  # "heuristic" or "llm:<model>"
    scored_at: datetime
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0


def llm_output_schema() -> dict:
    """JSON schema for structured outputs: flat, every field required, no extra keys.

    Pydantic emits keywords the structured-output validator does not accept (titles,
    numeric bounds), so the schema is built here explicitly and ranges are enforced by
    `JobScore.clamped()` after parsing.
    """
    return {
        "type": "object",
        "properties": {
            "fit": {"type": "integer", "description": "0 (no fit) to 100 (ideal fit)"},
            "verdict": {"type": "string", "enum": ["strong", "possible", "weak"]},
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to five short reasons, most important first",
            },
            "visa_sponsorship": {"type": "string", "enum": ["yes", "no", "unknown"]},
            "language_requirement": {
                "type": "string",
                "enum": ["english", "german", "other", "unknown"],
            },
            "seniority": {"type": "string", "enum": ["junior", "mid", "senior", "unknown"]},
            "workplace": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unknown"]},
        },
        "required": [
            "fit",
            "verdict",
            "reasons",
            "visa_sponsorship",
            "language_requirement",
            "seniority",
            "workplace",
        ],
        "additionalProperties": False,
    }
