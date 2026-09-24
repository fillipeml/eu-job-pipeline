"""Lever postings API (public JSON per company slug, no key).

Endpoint: GET https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

import httpx

from ..models import Job
from .base import date_from_unix, guess_country, looks_remote, matches_any

BASE_URL = "https://api.lever.co/v0/postings/{company}"


class LeverSource:
    name = "lever"

    def __init__(self, client: httpx.Client, companies: list[str]) -> None:
        self.client = client
        self.companies = companies

    def fetch(self, queries: list[str]) -> list[Job]:
        jobs: list[Job] = []
        for company in self.companies:
            response = self.client.get(BASE_URL.format(company=company), params={"mode": "json"})
            response.raise_for_status()
            for raw in response.json():
                job = self.parse(raw, company)
                if matches_any(job.text(), queries):
                    jobs.append(job)
        return jobs

    @staticmethod
    def parse(raw: dict, company: str) -> Job:
        categories = raw.get("categories") or {}
        location = (categories.get("location") or "").strip()
        workplace = (raw.get("workplaceType") or "").lower()
        tags = [t for t in (categories.get("team"), categories.get("commitment")) if t]
        return Job(
            source="lever",
            external_id=f"{company}:{raw['id']}",
            title=(raw.get("text") or "").strip(),
            company=company.replace("-", " ").title(),
            location=location,
            country=guess_country(location),
            remote=True if workplace == "remote" else looks_remote(location, workplace),
            url=raw.get("hostedUrl", ""),
            description=(raw.get("descriptionPlain") or "").strip(),
            posted_at=date_from_unix(raw.get("createdAt")),
            tags=tags,
        )
