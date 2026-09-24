from datetime import date

import pytest

from eu_job_pipeline.sources import (
    ArbeitnowSource,
    BundesagenturSource,
    GreenhouseSource,
    LeverSource,
)
from eu_job_pipeline.sources.base import guess_country, matches_any, strip_html


def test_arbeitnow_parses_and_filters(http_client):
    jobs = ArbeitnowSource(http_client, pages=2).fetch(["engineer"])
    titles = {j.title for j in jobs}
    assert titles == {"AI Engineer", "Senior Data Engineer"}
    ai = next(j for j in jobs if j.title == "AI Engineer")
    assert ai.country == "DE" and ai.company == "Nordlicht Analytics GmbH"
    assert "<p>" not in ai.description and "visa sponsorship" in ai.description.lower()
    assert "Python" in ai.tags and ai.posted_at == date(2026, 9, 20)


def test_bundesagentur_parses_list_endpoint(http_client):
    jobs = BundesagenturSource(http_client).fetch(["Data Engineer"])
    assert len(jobs) == 3
    first = jobs[0]
    assert first.country == "DE" and first.location == "München, Bayern"
    assert first.url.startswith("https://example.com")  # externeUrl wins
    assert jobs[1].url.endswith("/jobdetail/10000-1000000002-S")  # fallback detail URL
    assert first.posted_at == date(2026, 9, 20)
    assert jobs[1].remote is True  # "Remote möglich" in the title


def test_greenhouse_unescapes_content(http_client):
    jobs = GreenhouseSource(http_client, ["demo-board"]).fetch(["engineer"])
    assert {j.title for j in jobs} == {"LLM Engineer", "Staff Platform Engineer"}
    llm = next(j for j in jobs if j.title == "LLM Engineer")
    assert llm.country == "SE" and "&lt;" not in llm.description
    assert "Fjord ML AB builds" in llm.description
    assert llm.external_id == "demo-board:7000000001"


def test_lever_parses_postings(http_client):
    jobs = LeverSource(http_client, ["demo-company"]).fetch(["engineer"])
    assert len(jobs) == 2
    de = next(j for j in jobs if j.title == "Data Engineer")
    assert de.country == "PT" and de.remote is True and de.posted_at == date(2026, 9, 18)
    assert "Data" in de.tags


def test_dedup_across_queries(http_client):
    # The same reference number returned for two queries must appear once.
    jobs = BundesagenturSource(http_client).fetch(["Data Engineer", "Machine Learning"])
    assert len(jobs) == 3


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Berlin", "DE"),
        ("München, Bayern", "DE"),
        ("Amsterdam, Netherlands", "NL"),
        ("Dublin", "IE"),
        ("Lisboa", "PT"),
        ("Remote - Europe", "EU"),
        ("Zürich", "CH"),
        ("Somewhere", None),
        ("", None),
    ],
)
def test_guess_country(location, expected):
    assert guess_country(location) == expected


def test_strip_html_keeps_line_breaks():
    text = strip_html("<p>One</p><ul><li>Two</li><li>Three &amp; four</li></ul>")
    assert text.splitlines()[0] == "One"
    assert "Three & four" in text and "<" not in text


def test_matches_any_requires_all_words_of_a_query():
    assert matches_any("senior data engineer wanted", ["data engineer"])
    assert not matches_any("data analyst wanted", ["data engineer"])
    assert matches_any("anything", [])
