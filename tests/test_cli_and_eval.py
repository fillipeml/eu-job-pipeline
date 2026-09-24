from pathlib import Path

from typer.testing import CliRunner

from eu_job_pipeline.cli import app
from eu_job_pipeline.evals import load_golden, run_eval
from eu_job_pipeline.scoring import HeuristicScorer

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _env(tmp_path, demo="true"):
    return {
        "DEMO_MODE": demo,
        "DB_PATH": str(tmp_path / "jobs.sqlite"),
        "FIXTURES_DIR": str(ROOT / "fixtures"),
        "PROFILE_PATH": str(ROOT / "profile.example.md"),
    }


def test_full_demo_flow(tmp_path):
    env = _env(tmp_path)
    r = runner.invoke(app, ["seed", "--count", "25"], env=env)
    assert r.exit_code == 0 and "seeded 25 new" in r.output

    r = runner.invoke(app, ["fetch"], env=env)
    assert (
        r.exit_code == 0 and "total new 8" in r.output
    )  # 2 + 3 + 1 + 2 fixture postings match the default queries

    r = runner.invoke(app, ["score"], env=env)
    assert r.exit_code == 0 and "heuristic" in r.output and "scored 33" in r.output

    r = runner.invoke(app, ["report", "--top", "5"], env=env)
    assert r.exit_code == 0 and "| 1 |" in r.output and "https://example.com" in r.output

    r = runner.invoke(
        app, ["report", "--format", "csv", "--out", str(tmp_path / "out.csv")], env=env
    )
    assert r.exit_code == 0 and (tmp_path / "out.csv").read_text(encoding="utf-8").startswith(
        "fit,verdict"
    )

    r = runner.invoke(app, ["stats"], env=env)
    assert r.exit_code == 0 and "jobs: 33" in r.output

    r = runner.invoke(app, ["score"], env=env)
    assert "nothing to score" in r.output


def test_seed_refuses_outside_demo_mode(tmp_path):
    r = runner.invoke(app, ["seed"], env=_env(tmp_path, demo="false"))
    assert r.exit_code == 2


def test_eval_command_runs_heuristic(tmp_path):
    r = runner.invoke(
        app, ["eval", "--golden", str(ROOT / "evals" / "golden.jsonl")], env=_env(tmp_path)
    )
    assert r.exit_code == 0 and "golden set: 20 postings" in r.output


def test_heuristic_meets_golden_thresholds(profile):
    report = run_eval(
        HeuristicScorer(
            profile,
            ["DE", "NL", "IE", "PT", "SE", "DK", "FI", "NO", "AT", "CH", "BE", "ES", "FR", "EU"],
        ),
        load_golden(ROOT / "evals" / "golden.jsonl"),
    )
    assert not report.unscored
    assert report.accuracy("visa_sponsorship") >= 0.9
    assert report.accuracy("language_requirement") >= 0.85
    assert report.accuracy("seniority") >= 0.85
    assert report.accuracy("verdict") >= 0.7
