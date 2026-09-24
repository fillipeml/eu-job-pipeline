"""Scorers: the deterministic heuristic and the LLM scorer with its clients."""

from typing import Protocol

from ..models import Job, ScoreRecord
from .heuristic import HeuristicScorer
from .llm import (
    AnthropicLLMClient,
    FixtureLLMClient,
    FixtureMissError,
    LLMClient,
    LLMResult,
    LLMScorer,
    RecordingLLMClient,
    request_hash,
)
from .profile import Profile, load_profile, parse_profile


class Scorer(Protocol):
    name: str

    def score(self, job: Job) -> ScoreRecord | None: ...


__all__ = [
    "AnthropicLLMClient",
    "FixtureLLMClient",
    "FixtureMissError",
    "HeuristicScorer",
    "LLMClient",
    "LLMResult",
    "LLMScorer",
    "Profile",
    "RecordingLLMClient",
    "Scorer",
    "load_profile",
    "parse_profile",
    "request_hash",
]
