from eu_job_pipeline.models import Job
from eu_job_pipeline.scoring import HeuristicScorer

TARGETS = ["DE", "NL", "IE", "PT", "EU"]


def _job(title, description, country="DE", remote=None):
    return Job(
        source="t",
        external_id=title.lower().replace(" ", "-"),
        title=title,
        company="Acme",
        location="Berlin",
        country=country,
        remote=remote,
        url="https://example.com",
        description=description,
    )


def test_strong_match_scores_high(profile):
    job = _job(
        "AI Engineer",
        "Python, SQL, LLM, Claude API, RAG, structured outputs, evaluation, Docker, GitHub Actions, AWS. "
        "English-speaking team. We offer visa sponsorship and relocation support.",
    )
    rec = HeuristicScorer(profile, TARGETS).score(job)
    assert rec.score.verdict == "strong" and rec.score.fit >= 70
    assert rec.score.visa_sponsorship == "yes"
    assert rec.score.language_requirement == "english"
    assert rec.scorer == "heuristic"


def test_german_and_seniority_penalties(profile):
    job = _job("Senior Data Engineer", "Python, SQL. 6+ years. Fluent German (C1) is required.")
    rec = HeuristicScorer(profile, TARGETS).score(job)
    assert rec.score.language_requirement == "german"
    assert rec.score.seniority == "senior"
    assert rec.score.verdict == "weak"
    assert any("German" in r for r in rec.score.reasons)


def test_work_permit_requirement_kills_the_score(profile):
    job = _job(
        "Data Engineer",
        "Python, SQL, ETL, AWS, Docker. Applicants must already hold a valid EU work permit.",
    )
    rec = HeuristicScorer(profile, TARGETS).score(job)
    assert rec.score.visa_sponsorship == "no"
    assert rec.score.fit < 45


def test_german_as_a_plus_is_not_a_requirement(profile):
    job = _job("Data Engineer", "Python, SQL, ETL. English working language; German is a plus.")
    rec = HeuristicScorer(profile, TARGETS).score(job)
    assert rec.score.language_requirement == "english"


def test_outside_target_countries_is_penalised(profile):
    inside = HeuristicScorer(profile, TARGETS).score(
        _job("Data Engineer", "Python, SQL, ETL.", country="DE")
    )
    outside = HeuristicScorer(profile, TARGETS).score(
        _job("Data Engineer", "Python, SQL, ETL.", country="US")
    )
    assert inside.score.fit > outside.score.fit


def test_workplace_detection(profile):
    scorer = HeuristicScorer(profile, TARGETS)
    assert (
        scorer.score(_job("AI Engineer", "Fully remote within the EU.")).score.workplace == "remote"
    )
    assert (
        scorer.score(_job("AI Engineer", "Hybrid, three days on site.")).score.workplace == "hybrid"
    )
    assert (
        scorer.score(_job("AI Engineer", "Nothing about the office.")).score.workplace == "unknown"
    )


def test_deterministic(profile):
    job = _job("AI Engineer", "Python, LLM, evaluation.")
    scorer = HeuristicScorer(profile, TARGETS)
    assert scorer.score(job).score == scorer.score(job).score
