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


def test_cost_estimate_uses_cache_discount():
    usage = {
        "scorer": "llm:claude-opus-5",
        "scored": 100,
        "input_tokens": 200_000,
        "output_tokens": 10_000,
        "cache_read_tokens": 150_000,
    }
    # uncached 50k @ $5 + cached 150k @ $0.5 + output 10k @ $25, per million
    assert estimate_cost_usd(usage) == round((50_000 * 5 + 150_000 * 0.5 + 10_000 * 25) / 1e6, 4)
    assert estimate_cost_usd({**usage, "scorer": "heuristic"}) is None


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
