"""Reports: a Markdown digest of the best matches, a CSV export and a cost summary."""

from __future__ import annotations

import csv
import io

from .models import Job, ScoreRecord

# USD per million tokens (input, output); cache reads are billed at 10 % of input.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def render_markdown(rows: list[tuple[Job, ScoreRecord]], title: str = "Top matches") -> str:
    out = [f"# {title}", "", f"{len(rows)} postings, best fit first.", ""]
    out += [
        "| # | Fit | Verdict | Title | Company | Location | Visa | Language | Seniority | Workplace |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, (job, rec) in enumerate(rows, 1):
        s = rec.score
        out.append(
            f"| {i} | {s.fit} | {s.verdict} | [{_esc(job.title)}]({job.url}) | {_esc(job.company)} | "
            f"{_esc(job.location) or '-'} | {s.visa_sponsorship} | {s.language_requirement} | "
            f"{s.seniority} | {s.workplace} |"
        )
    out.append("")
    for i, (job, rec) in enumerate(rows[:10], 1):
        out.append(f"## {i}. {job.title} - {job.company} ({rec.score.fit}, {rec.scorer})")
        out += [f"- {r}" for r in rec.score.reasons]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_csv(rows: list[tuple[Job, ScoreRecord]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "fit",
            "verdict",
            "title",
            "company",
            "location",
            "country",
            "visa",
            "language",
            "seniority",
            "workplace",
            "posted_at",
            "source",
            "url",
            "scorer",
            "reasons",
        ]
    )
    for job, rec in rows:
        s = rec.score
        writer.writerow(
            [
                s.fit,
                s.verdict,
                job.title,
                job.company,
                job.location,
                job.country or "",
                s.visa_sponsorship,
                s.language_requirement,
                s.seniority,
                s.workplace,
                job.posted_at or "",
                job.source,
                job.url,
                rec.scorer,
                " | ".join(s.reasons),
            ]
        )
    return buf.getvalue()


#: What a cached token costs relative to an ordinary input token. Reads are the cheap side of
#: the bargain; the request that writes an entry pays a premium for it.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


def estimate_cost_usd(usage: dict, prices: dict[str, tuple[float, float]] = PRICES) -> float | None:
    """Cost of what a scorer actually spent, from the stored token counts.

    The three input counts do not overlap. ``input_tokens`` is already the uncached remainder,
    not the whole prompt: the full prompt is ``input_tokens + cache_write + cache_read``. An
    earlier version subtracted the cached reads from ``input_tokens`` before billing them,
    which discounted the same tokens twice and understated a cached run by about half.
    """
    model = usage["scorer"].removeprefix("llm:")
    if model not in prices:
        return None
    in_price, out_price = prices[model]
    cost = (
        usage["input_tokens"] * in_price
        + usage["cache_read_tokens"] * in_price * CACHE_READ_MULTIPLIER
        + usage.get("cache_write_tokens", 0) * in_price * CACHE_WRITE_MULTIPLIER
        + usage["output_tokens"] * out_price
    ) / 1e6
    return round(cost, 4)


def render_stats(stats: dict) -> str:
    out = [f"jobs: {stats['jobs']}  scored: {stats['scored']}", ""]
    out.append(
        "by source:  " + ", ".join(f"{k}={v}" for k, v in sorted(stats["by_source"].items()))
    )
    out.append(
        "by country: " + ", ".join(f"{k}={v}" for k, v in sorted(stats["by_country"].items()))
    )
    out.append(
        "by verdict: " + ", ".join(f"{k}={v}" for k, v in sorted(stats["by_verdict"].items()))
    )
    if stats["usage"]:
        out += [
            "",
            "| Scorer | Scored | Input tok | Cached | Output tok | Avg latency | Cost | Cost / 1,000 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for u in stats["usage"]:
            cost = estimate_cost_usd(u)
            per_k = f"${cost / u['scored'] * 1000:.2f}" if cost is not None and u["scored"] else "-"
            cost_text = f"${cost}" if cost is not None else "-"
            out.append(
                f"| {u['scorer']} | {u['scored']} | {u['input_tokens']} | {u['cache_read_tokens']} | "
                f"{u['output_tokens']} | {u['avg_latency_ms']} ms | {cost_text} | {per_k} |"
            )
    return "\n".join(out) + "\n"


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
