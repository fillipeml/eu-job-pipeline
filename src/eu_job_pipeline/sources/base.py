"""Shared plumbing for job sources: the interface, HTML stripping and country guessing."""

from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime
from typing import Protocol

import httpx

from ..models import Job


class JobSource(Protocol):
    """Every source fetches postings for a list of search terms and returns normalised jobs."""

    name: str

    def fetch(self, queries: list[str]) -> list[Job]: ...


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


def strip_html(text: str | None) -> str:
    """HTML (possibly entity-escaped, as Greenhouse returns it) to readable plain text."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    unescaped = re.sub(r"(?i)<\s*(br|/p|/li|/h[1-6]|/div|/tr)\s*/?>", "\n", unescaped)
    plain = _TAG_RE.sub(" ", unescaped)
    plain = _WS_RE.sub(" ", plain)
    plain = "\n".join(line.strip() for line in plain.splitlines())
    return _NL_RE.sub("\n\n", plain).strip()


def matches_any(text: str, queries: list[str]) -> bool:
    """Client-side filter for sources without server-side search."""
    if not queries:
        return True
    lowered = text.lower()
    return any(
        all(re.search(rf"\b{re.escape(word)}\b", lowered) for word in q.lower().split())
        for q in queries
    )


# Minimal gazetteer: enough to bucket European postings by country without a geocoder.
_COUNTRY_HINTS: dict[str, tuple[str, ...]] = {
    "DE": (
        "germany",
        "deutschland",
        "berlin",
        "munich",
        "münchen",
        "hamburg",
        "frankfurt",
        "cologne",
        "köln",
        "stuttgart",
        "düsseldorf",
        "leipzig",
        "dresden",
        "nuremberg",
        "karlsruhe",
    ),
    "NL": (
        "netherlands",
        "nederland",
        "amsterdam",
        "rotterdam",
        "utrecht",
        "eindhoven",
        "the hague",
        "den haag",
    ),
    "IE": ("ireland", "dublin", "cork", "galway"),
    "PT": ("portugal", "lisbon", "lisboa", "porto", "braga"),
    "SE": ("sweden", "sverige", "stockholm", "gothenburg", "göteborg", "malmö"),
    "DK": ("denmark", "danmark", "copenhagen", "københavn", "aarhus"),
    "FI": ("finland", "suomi", "helsinki", "tampere"),
    "NO": ("norway", "norge", "oslo", "bergen"),
    "AT": ("austria", "österreich", "vienna", "wien", "graz"),
    "CH": ("switzerland", "schweiz", "zurich", "zürich", "geneva", "basel", "lausanne"),
    "BE": ("belgium", "belgië", "brussels", "bruxelles", "antwerp", "ghent"),
    "ES": ("spain", "españa", "madrid", "barcelona", "valencia", "málaga"),
    "FR": ("france", "paris", "lyon", "toulouse", "nantes"),
    "IT": ("italy", "italia", "milan", "milano", "rome", "roma"),
    "PL": ("poland", "polska", "warsaw", "warszawa", "kraków", "krakow", "wrocław"),
    "CZ": ("czech", "prague", "praha"),
    "GB": ("united kingdom", "england", "london", "manchester", "edinburgh", "uk"),
    "EU": ("europe", "eu-wide", "emea", "european union"),
}
_COUNTRY_CODE_RE = re.compile(r"\b(DE|NL|IE|PT|SE|DK|FI|NO|AT|CH|BE|ES|FR|IT|PL|CZ|GB)\b")


def guess_country(location: str | None) -> str | None:
    if not location:
        return None
    lowered = location.lower()
    for code, hints in _COUNTRY_HINTS.items():
        if any(h in lowered for h in hints):
            return code
    m = _COUNTRY_CODE_RE.search(location)
    return m.group(1) if m else None


def looks_remote(*parts: str | None) -> bool | None:
    joined = " ".join(p for p in parts if p).lower()
    if not joined:
        return None
    if "remote" in joined or "home office" in joined or "homeoffice" in joined:
        return True
    return None


def date_from_unix(value: int | float | None) -> date | None:
    if value is None:
        return None
    seconds = value / 1000 if value > 10_000_000_000 else value
    return datetime.fromtimestamp(seconds, tz=UTC).date()


def date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def make_client(
    timeout: float = 20.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        transport=transport,
        headers={
            "User-Agent": "eu-job-pipeline/0.1 (+https://github.com/fillipeml/eu-job-pipeline)"
        },
        follow_redirects=True,
    )
