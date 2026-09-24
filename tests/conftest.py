from __future__ import annotations

from pathlib import Path

import pytest

from eu_job_pipeline.demo import fixture_transport, generate_jobs
from eu_job_pipeline.scoring import load_profile
from eu_job_pipeline.sources import make_client
from eu_job_pipeline.store import Store

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def http_client(fixtures_dir):
    with make_client(transport=fixture_transport(fixtures_dir)) as client:
        yield client


@pytest.fixture
def profile():
    return load_profile(ROOT / "profile.example.md")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.sqlite")
    yield s
    s.close()


@pytest.fixture
def sample_jobs():
    return generate_jobs(30, seed=1)
