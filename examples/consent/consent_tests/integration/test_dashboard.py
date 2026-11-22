"""The Grafana dashboard queries only exported metrics, and its SQL runs on the schema."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

import consent_app.adapters.reporting
import consent_app.factory  # noqa: F401 — registers the request metrics
from consent_app.adapters.seed import seed_demo_data
from consent_app.container import build_consent
from consent_app.settings import ConsentSettings

DASHBOARD: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "grafana" / "consent-dashboard.json").read_text()
)
TARGETS = [(p["title"], t) for p in DASHBOARD["panels"] for t in p.get("targets", [])]
SQL = [(title, t["rawSql"]) for title, t in TARGETS if "rawSql" in t]


def _exported() -> set[str]:
    names: set[str] = set()
    for family in REGISTRY.collect():
        names |= {family.name, f"{family.name}_total"} | {s.name for s in family.samples}
    return names


def test_every_consentapp_metric_on_the_dashboard_exists() -> None:
    used = {m for _, t in TARGETS for m in re.findall(r"\bconsentapp_[a-z_]+", t.get("expr", ""))}

    assert used, "the dashboard queries no consentapp_* metric"
    assert sorted(used - _exported()) == []


@pytest.fixture
async def seeded_db(database_url: str, db_path: str) -> str:
    domain = await build_consent(
        ConsentSettings(_env_file=None, DATABASE_URL=SecretStr(database_url))  # type: ignore[call-arg]  # pydantic-settings init kwarg
    )
    await seed_demo_data(domain, environment="development")
    await domain.aclose()
    return db_path


@pytest.mark.parametrize(("title", "sql"), SQL, ids=[t for t, _ in SQL])
def test_sql_panel_returns_seeded_rows(title: str, sql: str, seeded_db: str) -> None:
    with closing(sqlite3.connect(seeded_db)) as conn:
        rows = conn.execute(sql).fetchall()

    assert rows, f"{title!r} shows nothing for the demo data"


def test_datasources_are_variables_so_provisioning_works() -> None:
    names = {v["name"] for v in DASHBOARD["templating"]["list"]}

    assert {"prometheus", "postgres", "job"} <= names
    assert "${DS_PROMETHEUS}" not in json.dumps(DASHBOARD)
