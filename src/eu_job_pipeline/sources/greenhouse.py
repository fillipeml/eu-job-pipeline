"""Greenhouse job boards (many European scale-ups publish through it).

Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
One request per configured board token; no key required.
"""

from __future__ import annotations

import httpx

from ..models import Job
from .base import date_from_iso, guess_country, looks_remote, matches_any, strip_html

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


class GreenhouseSource:
    name = "greenhouse"

    def __init__(self, client: httpx.Client, boards: list[str]) -> None:
        self.client = client
        self.boards = boards

    def fetch(self, queries: list[str]) -> list[Job]:
        jobs: list[Job] = []
        for board in self.boards:
            response = self.client.get(BASE_URL.format(board=board), params={"content": "true"})
            response.raise_for_status()
            for raw in response.json().get("jobs", []):
                job = self.parse(raw, board)
                if matches_any(job.text(), queries):
                    jobs.append(job)
        return jobs

    @staticmethod
    def parse(raw: dict, board: str) -> Job:
        location = ((raw.get("location") or {}).get("name") or "").strip()
        departments = [d.get("name", "") for d in raw.get("departments", []) if d.get("name")]
        return Job(
            source="greenhouse",
            external_id=f"{board}:{raw['id']}",
            title=(raw.get("title") or "").strip(),
            company=(raw.get("company_name") or board.replace("-", " ").title()).strip(),
            location=location,
            country=guess_country(location),
            remote=looks_remote(location, raw.get("title")),
            url=raw.get("absolute_url", ""),
            description=strip_html(raw.get("content")),
            posted_at=date_from_iso(raw.get("updated_at")),
            tags=departments,
        )
