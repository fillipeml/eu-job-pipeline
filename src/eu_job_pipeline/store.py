"""SQLite persistence. One file, two tables, idempotent writes.

Jobs are keyed by `source:external_id`, so fetching the same posting twice updates
`last_seen` instead of creating a duplicate. Scores are keyed by job and overwritten on
re-score, keeping the scorer name and token usage for the cost report.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from .models import Job, JobScore, ScoreRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    country     TEXT,
    remote      INTEGER,
    url         TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    posted_at   TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    job_key              TEXT PRIMARY KEY REFERENCES jobs(key) ON DELETE CASCADE,
    fit                  INTEGER NOT NULL,
    verdict              TEXT NOT NULL,
    reasons              TEXT NOT NULL,
    visa_sponsorship     TEXT NOT NULL,
    language_requirement TEXT NOT NULL,
    seniority            TEXT NOT NULL,
    workplace            TEXT NOT NULL,
    scorer               TEXT NOT NULL,
    scored_at            TEXT NOT NULL,
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    latency_ms           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scores_fit ON scores(fit DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ jobs
    def upsert_jobs(self, jobs: Iterable[Job]) -> tuple[int, int]:
        """Insert new jobs, refresh existing ones. Returns (new, updated)."""
        now = _now()
        new = updated = 0
        with self.conn:
            for job in jobs:
                exists = self.conn.execute(
                    "SELECT 1 FROM jobs WHERE key = ?", (job.key,)
                ).fetchone()
                self.conn.execute(
                    """
                    INSERT INTO jobs (key, source, external_id, title, company, location, country,
                                      remote, url, description, posted_at, tags, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        title = excluded.title, company = excluded.company,
                        location = excluded.location, country = excluded.country,
                        remote = excluded.remote, url = excluded.url,
                        description = excluded.description, posted_at = excluded.posted_at,
                        tags = excluded.tags, last_seen = excluded.last_seen
                    """,
                    (
                        job.key,
                        job.source,
                        job.external_id,
                        job.title,
                        job.company,
                        job.location,
                        job.country,
                        None if job.remote is None else int(job.remote),
                        job.url,
                        job.description,
                        job.posted_at.isoformat() if job.posted_at else None,
                        json.dumps(job.tags, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                if exists:
                    updated += 1
                else:
                    new += 1
        return new, updated

    def jobs(self, *, unscored_only: bool = False, limit: int = 0) -> list[Job]:
        sql = "SELECT j.* FROM jobs j"
        if unscored_only:
            sql += " LEFT JOIN scores s ON s.job_key = j.key WHERE s.job_key IS NULL"
        sql += " ORDER BY j.posted_at DESC NULLS LAST, j.key"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self.conn.execute(sql)]

    def get_job(self, key: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE key = ?", (key,)).fetchone()
        return _row_to_job(row) if row else None

    def clear(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM scores")
            self.conn.execute("DELETE FROM jobs")

    # ---------------------------------------------------------------- scores
    def save_score(self, record: ScoreRecord) -> None:
        s = record.score
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO scores (job_key, fit, verdict, reasons, visa_sponsorship,
                                    language_requirement, seniority, workplace, scorer, scored_at,
                                    input_tokens, output_tokens, cache_read_tokens, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    fit = excluded.fit, verdict = excluded.verdict, reasons = excluded.reasons,
                    visa_sponsorship = excluded.visa_sponsorship,
                    language_requirement = excluded.language_requirement,
                    seniority = excluded.seniority, workplace = excluded.workplace,
                    scorer = excluded.scorer, scored_at = excluded.scored_at,
                    input_tokens = excluded.input_tokens, output_tokens = excluded.output_tokens,
                    cache_read_tokens = excluded.cache_read_tokens, latency_ms = excluded.latency_ms
                """,
                (
                    record.job_key,
                    s.fit,
                    s.verdict,
                    json.dumps(s.reasons, ensure_ascii=False),
                    s.visa_sponsorship,
                    s.language_requirement,
                    s.seniority,
                    s.workplace,
                    record.scorer,
                    record.scored_at.isoformat(),
                    record.input_tokens,
                    record.output_tokens,
                    record.cache_read_tokens,
                    record.latency_ms,
                ),
            )

    def ranked(self, *, top: int = 0, min_fit: int = 0) -> list[tuple[Job, ScoreRecord]]:
        sql = """
            SELECT j.*, s.fit, s.verdict, s.reasons, s.visa_sponsorship, s.language_requirement,
                   s.seniority, s.workplace, s.scorer, s.scored_at, s.input_tokens, s.output_tokens,
                   s.cache_read_tokens, s.latency_ms
            FROM scores s JOIN jobs j ON j.key = s.job_key
            WHERE s.fit >= ?
            ORDER BY s.fit DESC, j.posted_at DESC NULLS LAST, j.key
        """
        if top:
            sql += f" LIMIT {int(top)}"
        return [(_row_to_job(r), _row_to_record(r)) for r in self.conn.execute(sql, (min_fit,))]

    def stats(self) -> dict:
        q = self.conn.execute
        by_source = {
            r["source"]: r["n"] for r in q("SELECT source, COUNT(*) n FROM jobs GROUP BY source")
        }
        by_country = {
            (r["country"] or "?"): r["n"]
            for r in q("SELECT country, COUNT(*) n FROM jobs GROUP BY country")
        }
        by_verdict = {
            r["verdict"]: r["n"]
            for r in q("SELECT verdict, COUNT(*) n FROM scores GROUP BY verdict")
        }
        usage = q(
            """SELECT COUNT(*) n, COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o,
                      COALESCE(SUM(cache_read_tokens),0) c, COALESCE(AVG(latency_ms),0) lat,
                      scorer FROM scores GROUP BY scorer"""
        ).fetchall()
        return {
            "jobs": q("SELECT COUNT(*) n FROM jobs").fetchone()["n"],
            "scored": q("SELECT COUNT(*) n FROM scores").fetchone()["n"],
            "by_source": by_source,
            "by_country": by_country,
            "by_verdict": by_verdict,
            "usage": [
                {
                    "scorer": r["scorer"],
                    "scored": r["n"],
                    "input_tokens": r["i"],
                    "output_tokens": r["o"],
                    "cache_read_tokens": r["c"],
                    "avg_latency_ms": int(r["lat"]),
                }
                for r in usage
            ],
        }


# ---------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        country=row["country"],
        remote=None if row["remote"] is None else bool(row["remote"]),
        url=row["url"],
        description=row["description"],
        posted_at=date.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
        tags=json.loads(row["tags"]),
    )


def _row_to_record(row: sqlite3.Row) -> ScoreRecord:
    return ScoreRecord(
        job_key=row["key"],
        score=JobScore(
            fit=row["fit"],
            verdict=row["verdict"],
            reasons=json.loads(row["reasons"]),
            visa_sponsorship=row["visa_sponsorship"],
            language_requirement=row["language_requirement"],
            seniority=row["seniority"],
            workplace=row["workplace"],
        ),
        scorer=row["scorer"],
        scored_at=datetime.fromisoformat(row["scored_at"]),
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        latency_ms=row["latency_ms"],
    )
