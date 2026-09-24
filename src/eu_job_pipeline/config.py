"""Runtime settings, read once from the environment (and `.env`) by the factory.

`DEMO_MODE=true` swaps every external dependency for a local one: job sources read
recorded fixtures instead of the network, and scoring uses the deterministic heuristic
scorer instead of the LLM. Business logic never checks this flag directly.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TARGET_COUNTRIES = "DE,NL,IE,PT,SE,DK,FI,NO,AT,CH,BE,ES,FR,EU"
DEFAULT_QUERIES = "AI engineer,Data engineer,LLM engineer,Machine learning engineer"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = False
    db_path: Path | None = None
    profile_path: Path = Path("profile.md")
    fixtures_dir: Path = Path("fixtures")

    # LLM scoring (live mode only)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = Field(default="medium", pattern="^(low|medium|high|xhigh|max)$")
    llm_max_tokens: int = 1024

    # Sources
    target_countries: str = DEFAULT_TARGET_COUNTRIES
    queries: str = DEFAULT_QUERIES
    arbeitnow_pages: int = 3
    bundesagentur_page_size: int = 100
    greenhouse_boards: str = ""  # comma-separated board tokens, e.g. "legora,pandektes"
    lever_companies: str = ""  # comma-separated Lever slugs
    http_timeout_seconds: float = 20.0

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path is not None:
            return self.db_path
        return Path(".demo/jobs.sqlite") if self.demo_mode else Path("data/jobs.sqlite")

    @property
    def country_list(self) -> list[str]:
        return _split(self.target_countries)

    @property
    def query_list(self) -> list[str]:
        return _split(self.queries)

    @property
    def greenhouse_board_list(self) -> list[str]:
        return _split(self.greenhouse_boards)

    @property
    def lever_company_list(self) -> list[str]:
        return _split(self.lever_companies)


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
