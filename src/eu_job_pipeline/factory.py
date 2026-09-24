"""The only place that reads `DEMO_MODE` and decides real vs local implementations."""

from __future__ import annotations

from pathlib import Path

import httpx

from .config import Settings
from .demo import fixture_transport
from .scoring import (
    AnthropicLLMClient,
    FixtureLLMClient,
    HeuristicScorer,
    LLMScorer,
    Profile,
    RecordingLLMClient,
    Scorer,
    load_profile,
)
from .sources import (
    ArbeitnowSource,
    BundesagenturSource,
    GreenhouseSource,
    JobSource,
    LeverSource,
    make_client,
)
from .store import Store

PROFILE_FALLBACK = Path("profile.example.md")


def build_store(settings: Settings) -> Store:
    return Store(settings.resolved_db_path)


def build_http_client(settings: Settings) -> httpx.Client:
    transport = fixture_transport(settings.fixtures_dir) if settings.demo_mode else None
    return make_client(timeout=settings.http_timeout_seconds, transport=transport)


def build_sources(
    settings: Settings, client: httpx.Client, only: list[str] | None = None
) -> list[JobSource]:
    sources: list[JobSource] = [
        ArbeitnowSource(client, pages=settings.arbeitnow_pages),
        BundesagenturSource(client, page_size=settings.bundesagentur_page_size),
    ]
    boards = settings.greenhouse_board_list or (["demo-board"] if settings.demo_mode else [])
    companies = settings.lever_company_list or (["demo-company"] if settings.demo_mode else [])
    if boards:
        sources.append(GreenhouseSource(client, boards))
    if companies:
        sources.append(LeverSource(client, companies))
    if only:
        wanted = {name.lower() for name in only}
        sources = [s for s in sources if s.name in wanted]
    return sources


def build_profile(settings: Settings) -> Profile:
    return load_profile(settings.profile_path, PROFILE_FALLBACK)


def build_scorer(settings: Settings, profile: Profile, mode: str | None = None) -> Scorer:
    """`mode`: None (follow settings), "heuristic", "llm", "fixture" or "record"."""
    heuristic = HeuristicScorer(profile, settings.country_list)
    mode = mode or ("heuristic" if settings.demo_mode else "llm")
    if mode == "heuristic":
        return heuristic
    if mode == "fixture":
        return LLMScorer(
            FixtureLLMClient(settings.fixtures_dir / "llm", settings.anthropic_model),
            profile,
            heuristic,
        )
    real = AnthropicLLMClient(
        model=settings.anthropic_model,
        effort=settings.anthropic_effort,
        max_tokens=settings.llm_max_tokens,
        api_key=settings.anthropic_api_key,
    )
    if mode == "record":
        return LLMScorer(
            RecordingLLMClient(real, settings.fixtures_dir / "llm"), profile, heuristic
        )
    return LLMScorer(real, profile, heuristic)
