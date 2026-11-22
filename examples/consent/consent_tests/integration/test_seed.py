"""The demo seed: realistic, rule-abiding, reproducible, re-runnable, never in production."""

import os
import sqlite3
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import SecretStr

from consent_app.adapters.seed import SUBJECTS, SeedingRefusedError, seed_demo_data
from consent_app.container import ConsentDomain, build_consent
from consent_app.settings import ConsentSettings


async def _domain(url: str) -> ConsentDomain:
    return await build_consent(ConsentSettings(_env_file=None, DATABASE_URL=SecretStr(url)))  # type: ignore[call-arg]  # pydantic-settings init kwarg


@pytest.fixture
async def domain(database_url: str) -> AsyncIterator[ConsentDomain]:
    domain = await _domain(database_url)
    yield domain
    await domain.aclose()


def _events(db_path: str) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        return int(conn.execute("SELECT count(*) FROM consent_events").fetchone()[0])


async def test_the_seed_covers_every_state_and_obeys_the_profile(
    domain: ConsentDomain, db_path: str
) -> None:
    report = await seed_demo_data(domain, environment="development")

    assert report.purposes_created == 4
    assert set(report.states) == {"granted", "withdrawn", "renewal_required", "not_given"}
    assert sum(report.states.values()) == 4 * len(SUBJECTS)
    # The demo pre-ticked box is refused like a real one, and leaves no trace.
    assert report.refused == {"method_not_accepted": 1}
    assert _events(db_path) == report.recorded


async def test_a_rerun_replays_and_records_nothing(domain: ConsentDomain, db_path: str) -> None:
    first = await seed_demo_data(domain, environment="development")

    again = await seed_demo_data(domain, environment="development")

    assert (again.purposes_created, again.recorded) == (0, 0)
    assert again.replayed == first.recorded
    assert again.states == first.states
    assert _events(db_path) == first.recorded


async def test_the_data_is_the_same_on_every_machine(tmp_path: Path) -> None:
    reports = []
    for name in ("one", "two"):
        domain = await _domain(f"sqlite+aiosqlite:///{tmp_path / name}.db")
        reports.append((await seed_demo_data(domain, environment="development")).as_dict())
        await domain.aclose()

    assert reports[0] == reports[1]


async def test_seeding_is_refused_in_production(domain: ConsentDomain, db_path: str) -> None:
    with pytest.raises(SeedingRefusedError, match="production"):
        await seed_demo_data(domain, environment="production")

    assert _events(db_path) == 0


def test_the_command_reports_an_unavailable_database_in_one_line() -> None:
    env = os.environ | {"CONSENT_DATABASE_URL": "sqlite+aiosqlite:////nonexistent-dir/consent.db"}
    result = subprocess.run(
        [sys.executable, "-m", "consent_app.adapters.seed"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr.strip().startswith("seed failed, the database is unavailable")
    assert "Traceback" not in result.stderr
