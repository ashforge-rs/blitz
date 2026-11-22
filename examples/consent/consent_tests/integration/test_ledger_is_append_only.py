"""The database itself refuses to rewrite or erase consent evidence."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from consent_app.adapters.sql.database import Database
from consent_app.adapters.sql.tables import consent_events

SEED = (
    "INSERT INTO purposes (slug, description, notice_version, notice_published_at, created_at) "
    "VALUES ('ads', 'Ads', 'v1', '2026-01-01 00:00:00+00:00', '2026-01-01 00:00:00+00:00')",
    "INSERT INTO purpose_notices (purpose, notice_version, published_at) "
    "VALUES ('ads', 'v1', '2026-01-01 00:00:00+00:00')",
    "INSERT INTO consent_events (id, subject_id, purpose, decision, notice_version, method, "
    "source, recorded_by, profile, recorded_at) VALUES ('e1', 's1', 'ads', 'granted', 'v1', "
    "'checkbox', 'web', 'crm', 'gdpr', '2026-01-01 00:00:00+00:00')",
)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE consent_events SET decision = 'withdrawn' WHERE id = 'e1'",
        "DELETE FROM consent_events WHERE id = 'e1'",
    ],
    ids=["update", "delete"],
)
async def test_raw_sql_cannot_change_or_delete_an_event(db: Database, statement: str) -> None:
    async with db.transaction() as conn:
        for seed in SEED:
            await conn.execute(text(seed))

    async def tamper() -> None:
        async with db.transaction() as conn:
            await conn.execute(text(statement))

    with pytest.raises(DBAPIError, match="append-only"):
        await tamper()

    async with db.transaction(read_only=True) as conn:
        decision = (await conn.execute(select(consent_events.c.decision))).scalar_one()
        count = (await conn.execute(select(func.count()).select_from(consent_events))).scalar_one()
    assert (decision, count) == ("granted", 1)
