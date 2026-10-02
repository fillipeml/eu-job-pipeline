from datetime import UTC, datetime

from eu_job_pipeline.demo import generate_jobs
from eu_job_pipeline.models import JobScore, ScoreRecord
from eu_job_pipeline.report import estimate_cost_usd, render_csv, render_markdown, render_stats


def _rows(jobs):
    rows = []
    for i, job in enumerate(jobs):
        score = JobScore(
            fit=90 - i,
            verdict="strong",
            reasons=["Reason A", "Reason B"],
            visa_sponsorship="yes",
            language_requirement="english",
            seniority="mid",
            workplace="remote",
        )
        rows.append(
            (
                job,
                ScoreRecord(
                    job_key=job.key, score=score, scorer="heuristic", scored_at=datetime.now(UTC)
                ),
            )
        )
    return rows


def test_markdown_report_lists_rows_and_reasons(sample_jobs):
    md = render_markdown(_rows(sample_jobs[:3]))
    assert "| 1 | 90 | strong |" in md
    assert sample_jobs[0].url in md
    assert "- Reason A" in md


def test_csv_report_has_header_and_rows(sample_jobs):
    csv_text = render_csv(_rows(sample_jobs[:2]))
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("fit,verdict,title,company")
    assert len(lines) == 3


def test_cost_estimate_bills_each_token_once():
    """The three input counts do not overlap, so none of them is subtracted from another.

    The earlier version of this test asserted the behaviour of the earlier version of the
    code: it read `input_tokens` as the whole prompt and took the cached reads out of it. The
    API reports `input_tokens` as the uncached remainder already, so that discounted the same
    tokens twice and understated a cached run by about half. Both have been corrected here.
    """
    usage = {
        "scorer": "llm:claude-opus-5",
        "scored": 100,
        "input_tokens": 50_000,
        "output_tokens": 10_000,
        "cache_read_tokens": 150_000,
        "cache_write_tokens": 20_000,
    }
    # 50k uncached @ $5 + 150k read @ $0.50 + 20k written @ $6.25 + 10k output @ $25, per million
    assert estimate_cost_usd(usage) == round(
        (50_000 * 5 + 150_000 * 0.5 + 20_000 * 6.25 + 10_000 * 25) / 1e6, 4
    )
    assert estimate_cost_usd({**usage, "scorer": "heuristic"}) is None


def test_a_run_served_entirely_from_cache_still_costs_something():
    # The shape that made the old arithmetic collapse to zero: everything read from cache.
    usage = {
        "scorer": "llm:claude-opus-5",
        "scored": 100,
        "input_tokens": 0,
        "output_tokens": 10_000,
        "cache_read_tokens": 150_000,
    }
    assert estimate_cost_usd(usage) == round((150_000 * 0.5 + 10_000 * 25) / 1e6, 4)


def test_a_batch_custom_id_is_one_the_api_accepts():
    """Every job key is `source:id`, and the Batches API rejects a colon.

    Nothing caught this: the SDK types `custom_id` as a plain string, and no test exercised
    the batch path, so `score --batch` would have failed on its first live run with every
    request rejected at once.
    """
    import re

    from eu_job_pipeline.scoring.llm import batch_custom_id

    allowed = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    keys = ["arbeitnow:demo-0001", "bundesagentur:demo-0003", "greenhouse:a/b.c-acentuação"]
    ids = [batch_custom_id(k) for k in keys]
    assert all(allowed.match(i) for i in ids)
    assert len(set(ids)) == len(keys), "two different jobs must not share a custom_id"


def test_stats_render_includes_cost_table():
    stats = {
        "jobs": 10,
        "scored": 10,
        "by_source": {"demo": 10},
        "by_country": {"DE": 10},
        "by_verdict": {"strong": 4},
        "usage": [
            {
                "scorer": "llm:claude-opus-5",
                "scored": 10,
                "input_tokens": 20_000,
                "output_tokens": 1_000,
                "cache_read_tokens": 15_000,
                "avg_latency_ms": 900,
            }
        ],
    }
    text = render_stats(stats)
    assert "Cost / 1,000" in text and "llm:claude-opus-5" in text


def test_demo_data_is_deterministic_and_fictional():
    a, b = generate_jobs(40, seed=7), generate_jobs(40, seed=7)
    assert [j.title for j in a] == [j.title for j in b]
    assert len({j.key for j in a}) == 40
    assert all(j.url.startswith("https://example.com/") for j in a)
    assert all("synthetic demo data" in j.description for j in a)
