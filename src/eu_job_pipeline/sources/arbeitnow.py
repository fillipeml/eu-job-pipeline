"""Arbeitnow job board (Europe-wide, English-first, free public API, no key).

Endpoint: GET https://www.arbeitnow.com/api/job-board-api?page=N
The API has no server-side search, so postings are filtered client-side.
"""

from __future__ import annotations

import httpx

from ..models import Job
from .base import date_from_unix, guess_country, looks_remote, matches_any, strip_html

BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource:
    name = "arbeitnow"

    def __init__(self, client: httpx.Client, pages: int = 3) -> None:
        self.client = client
        self.pages = max(1, pages)

    def fetch(self, queries: list[str]) -> list[Job]:
        jobs: list[Job] = []
        for page in range(1, self.pages + 1):
            response = self.client.get(BASE_URL, params={"page": page})
            response.raise_for_status()
            payload = response.json()
            for raw in payload.get("data", []):
                job = self.parse(raw)
                if matches_any(job.text(), queries):
                    jobs.append(job)
            if not payload.get("links", {}).get("next"):
                break
        return jobs

    @staticmethod
    def parse(raw: dict) -> Job:
        location = raw.get("location") or ""
        remote = bool(raw.get("remote")) or looks_remote(location, raw.get("title"))
        return Job(
            source="arbeitnow",
            external_id=str(raw["slug"]),
            title=raw.get("title", "").strip(),
            company=raw.get("company_name", "").strip(),
            location=location,
            country=guess_country(location),
            remote=remote,
            url=raw.get("url", ""),
            description=strip_html(raw.get("description")),
            posted_at=date_from_unix(raw.get("created_at")),
            tags=[*raw.get("tags", []), *raw.get("job_types", [])],
        )
