"""Bundesagentur für Arbeit Jobsuche (Germany's public employment agency).

Endpoint: GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs
Header:   X-API-Key: jobboerse-jobsuche   (public key documented by the agency)
The list endpoint returns title, employer, place and reference number; the full text
needs a second call per posting, which this source skips on purpose (volume vs value).
"""

from __future__ import annotations

import httpx

from ..models import Job
from .base import date_from_iso, looks_remote

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
PUBLIC_API_KEY = "jobboerse-jobsuche"
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"


class BundesagenturSource:
    name = "bundesagentur"

    def __init__(self, client: httpx.Client, page_size: int = 100) -> None:
        self.client = client
        self.page_size = page_size

    def fetch(self, queries: list[str]) -> list[Job]:
        jobs: dict[str, Job] = {}
        for query in queries or [""]:
            response = self.client.get(
                BASE_URL,
                params={"was": query, "size": self.page_size, "page": 1, "angebotsart": 1},
                headers={"X-API-Key": PUBLIC_API_KEY},
            )
            response.raise_for_status()
            for raw in response.json().get("stellenangebote", []):
                job = self.parse(raw)
                jobs.setdefault(job.key, job)
        return list(jobs.values())

    @staticmethod
    def parse(raw: dict) -> Job:
        place = raw.get("arbeitsort") or {}
        location = ", ".join(p for p in (place.get("ort"), place.get("region")) if p)
        title = (raw.get("titel") or raw.get("beruf") or "").strip()
        occupation = (raw.get("beruf") or "").strip()
        ref = str(raw["refnr"])
        return Job(
            source="bundesagentur",
            external_id=ref,
            title=title,
            company=(raw.get("arbeitgeber") or "").strip(),
            location=location or "Germany",
            country="DE",
            remote=looks_remote(title, location),
            url=raw.get("externeUrl") or DETAIL_URL.format(ref=ref),
            description=occupation if occupation and occupation != title else "",
            posted_at=date_from_iso(raw.get("aktuelleVeroeffentlichungsdatum")),
            tags=[occupation] if occupation else [],
        )
