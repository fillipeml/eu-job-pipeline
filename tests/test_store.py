from datetime import UTC, datetime

from eu_job_pipeline.models import JobScore, ScoreRecord


def _record(job, fit=80):
    return ScoreRecord(
        job_key=job.key,
        score=JobScore(
            fit=fit,
            verdict="strong",
            reasons=["r"],
            visa_sponsorship="yes",
            language_requirement="english",
            seniority="mid",
            workplace="remote",
        ),
        scorer="test",
        scored_at=datetime.now(UTC),
        input_tokens=100,
        output_tokens=20,
    )


def test_upsert_is_idempotent(store, sample_jobs):
    assert store.upsert_jobs(sample_jobs) == (30, 0)
    assert store.upsert_jobs(sample_jobs) == (0, 30)
    assert len(store.jobs()) == 30


def test_upsert_refreshes_mutable_fields(store, sample_jobs):
    store.upsert_jobs(sample_jobs[:1])
    changed = sample_jobs[0].model_copy(update={"title": "Renamed role"})
    store.upsert_jobs([changed])
    assert store.get_job(changed.key).title == "Renamed role"
    assert len(store.jobs()) == 1


def test_unscored_filter_and_ranking(store, sample_jobs):
    store.upsert_jobs(sample_jobs)
    store.save_score(_record(sample_jobs[0], fit=90))
    store.save_score(_record(sample_jobs[1], fit=40))
    assert len(store.jobs(unscored_only=True)) == 28
    ranked = store.ranked()
    assert [r.score.fit for _, r in ranked] == [90, 40]
    assert store.ranked(min_fit=50)[0][0].key == sample_jobs[0].key
    assert len(store.ranked(top=1)) == 1


def test_save_score_overwrites(store, sample_jobs):
    store.upsert_jobs(sample_jobs[:1])
    store.save_score(_record(sample_jobs[0], fit=10))
    store.save_score(_record(sample_jobs[0], fit=75))
    assert store.ranked()[0][1].score.fit == 75


def test_stats_and_clear(store, sample_jobs):
    store.upsert_jobs(sample_jobs)
    store.save_score(_record(sample_jobs[0]))
    stats = store.stats()
    assert stats["jobs"] == 30 and stats["scored"] == 1
    assert sum(stats["by_source"].values()) == 30
    assert stats["usage"][0]["input_tokens"] == 100
    store.clear()
    assert store.stats()["jobs"] == 0
