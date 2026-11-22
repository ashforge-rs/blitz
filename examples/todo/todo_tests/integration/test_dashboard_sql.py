"""Every SQL panel of the dashboard runs against the real schema and shows seeded data."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from audit.backends.noop import NoopAuditBackend
from pydantic import SecretStr

from todo_app.cli.composition import open_services
from todo_app.cli.seed import seed_demo_data
from todo_app.settings import TodoSettings

DASHBOARD = Path(__file__).resolve().parents[2] / "grafana" / "todo-dashboard.json"
PANELS = [
    (p["title"], t["rawSql"])
    for p in json.loads(DASHBOARD.read_text())["panels"]
    for t in p.get("targets", [])
    if "rawSql" in t
]


@pytest.mark.parametrize(("title", "sql"), PANELS, ids=[t for t, _ in PANELS])
async def test_sql_panel_returns_seeded_rows(
    title: str, sql: str, database_url: str, db_path: str
) -> None:
    settings = TodoSettings(_env_file=None, DATABASE_URL=SecretStr(database_url))  # type: ignore[call-arg]  # pydantic-settings init kwarg
    async with open_services(settings, audit_backend=NoopAuditBackend()) as services:
        await seed_demo_data(services, environment="development")

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(sql).fetchall()

    assert rows, f"{title!r} shows nothing for the demo data"


def test_the_dashboard_has_sql_panels_and_no_email_column() -> None:
    assert len(PANELS) >= 2
    assert all("email" not in sql.lower() for _, sql in PANELS)
