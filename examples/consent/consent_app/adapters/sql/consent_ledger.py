from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    NoticeVersion,
    PurposeSlug,
    SubjectId,
)
from consent_app.ports import ConsentLedger, DecisionTally, EventIdTakenError

from .tables import consent_events

if TYPE_CHECKING:
    from sqlalchemy import RowMapping
    from sqlalchemy.ext.asyncio import AsyncConnection

_E = consent_events


class SqlConsentLedger(ConsentLedger):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def append(self, event: ConsentEvent) -> None:
        statement = _E.insert().values(
            id=event.id,
            subject_id=event.subject.value,
            purpose=event.purpose.value,
            decision=event.decision.value,
            notice_version=event.notice_version.value if event.notice_version else None,
            method=event.method.value if event.method else None,
            source=event.source,
            recorded_by=event.recorded_by,
            profile=event.profile,
            recorded_at=event.recorded_at,
        )
        try:
            await self._conn.execute(statement)
        except IntegrityError as exc:
            # The only unique constraint a caller can hit: the event id (concurrent retry).
            raise EventIdTakenError from exc

    async def get(self, event_id: str) -> ConsentEvent | None:
        row = (await self._conn.execute(select(_E).where(_E.c.id == event_id))).mappings().first()
        return None if row is None else _to_event(row)

    async def latest(self, subject: SubjectId, purpose: PurposeSlug) -> ConsentEvent | None:
        statement = (
            select(_E)
            .where(_E.c.subject_id == subject.value, _E.c.purpose == purpose.value)
            .order_by(_E.c.seq.desc())
            .limit(1)
        )
        row = (await self._conn.execute(statement)).mappings().first()
        return None if row is None else _to_event(row)

    async def latest_by_purpose(self, subject: SubjectId) -> dict[PurposeSlug, ConsentEvent]:
        newest = (
            select(func.max(_E.c.seq))
            .where(_E.c.subject_id == subject.value)
            .group_by(_E.c.purpose)
            .scalar_subquery()
        )
        rows = await self._conn.execute(select(_E).where(_E.c.seq.in_(newest)))
        events = [_to_event(r) for r in rows.mappings()]
        return {e.purpose: e for e in events}

    async def history(self, subject: SubjectId) -> list[ConsentEvent]:
        statement = select(_E).where(_E.c.subject_id == subject.value).order_by(_E.c.seq)
        return [_to_event(r) for r in (await self._conn.execute(statement)).mappings()]

    async def latest_decisions(self) -> list[ConsentEvent]:
        newest = select(func.max(_E.c.seq)).group_by(_E.c.subject_id, _E.c.purpose)
        rows = await self._conn.execute(select(_E).where(_E.c.seq.in_(newest.scalar_subquery())))
        return [_to_event(r) for r in rows.mappings()]

    async def subject_count(self) -> int:
        statement = select(func.count(func.distinct(_E.c.subject_id)))
        return int((await self._conn.execute(statement)).scalar_one())

    async def tallies(self) -> list[DecisionTally]:
        statement = select(_E.c.decision, _E.c.method, _E.c.source, func.count()).group_by(
            _E.c.decision, _E.c.method, _E.c.source
        )
        return [
            DecisionTally(
                ConsentDecision(decision), ConsentMethod(method) if method else None, source, count
            )
            for decision, method, source, count in await self._conn.execute(statement)
        ]


def _to_event(row: RowMapping) -> ConsentEvent:
    return ConsentEvent(
        id=row["id"],
        subject=SubjectId(row["subject_id"]),
        purpose=PurposeSlug(row["purpose"]),
        decision=ConsentDecision(row["decision"]),
        notice_version=NoticeVersion(row["notice_version"]) if row["notice_version"] else None,
        method=ConsentMethod(row["method"]) if row["method"] else None,
        source=row["source"],
        recorded_by=row["recorded_by"],
        profile=row["profile"],
        recorded_at=row["recorded_at"],
    )
