"""Port contract: the in-memory fake and every SQL backend behave alike."""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta

import pytest

from consent_app.adapters.sql.unit_of_work import SqlConsentUnitOfWorkFactory
from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    NoticeVersion,
    Purpose,
    PurposeSlug,
    SubjectId,
)
from consent_app.ports import (
    ConsentUnitOfWorkFactory,
    EventIdTakenError,
    PurposeExistsError,
    ReadOnlyUnitOfWorkError,
)
from consent_tests.fakes import EPOCH, InMemoryConsentUnitOfWorkFactory
from consent_tests.storage import BACKENDS, open_migrated, url_for

ADS, NEWS = PurposeSlug("ads"), PurposeSlug("newsletter")
ADA, BOB = SubjectId("subj-ada"), SubjectId("subj-bob")


def _purpose(slug: PurposeSlug = ADS, version: str = "v1") -> Purpose:
    return Purpose(slug, f"About {slug.value}", NoticeVersion(version), EPOCH, EPOCH)


def _event(
    event_id: str,
    subject: SubjectId = ADA,
    purpose: PurposeSlug = ADS,
    decision: ConsentDecision = ConsentDecision.GRANTED,
    minutes: int = 0,
) -> ConsentEvent:
    granted = decision is ConsentDecision.GRANTED
    return ConsentEvent(
        id=event_id,
        subject=subject,
        purpose=purpose,
        decision=decision,
        notice_version=NoticeVersion("v1") if granted else None,
        method=ConsentMethod.CHECKBOX if granted else None,
        source="web",
        recorded_by="crm",
        profile="gdpr",
        recorded_at=EPOCH + timedelta(minutes=minutes),
    )


@pytest.fixture(params=["in-memory", *BACKENDS])
async def uow(
    request: pytest.FixtureRequest, database_url: str
) -> AsyncIterator[ConsentUnitOfWorkFactory]:
    if request.param == "in-memory":
        yield InMemoryConsentUnitOfWorkFactory()
        return
    db = await open_migrated(await url_for(request.param, database_url))
    yield SqlConsentUnitOfWorkFactory(db)
    await db.close()


async def _seed(uow: ConsentUnitOfWorkFactory, *purposes: Purpose) -> None:
    async with uow() as unit:
        for purpose in purposes:
            await unit.purposes.add(purpose)


async def test_purposes_round_trip_in_slug_order(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose(NEWS), _purpose(ADS))

    async with uow(read_only=True) as unit:
        assert await unit.purposes.get(ADS) == _purpose(ADS)
        assert await unit.purposes.get(PurposeSlug("missing")) is None
        assert [p.slug for p in await unit.purposes.all()] == [ADS, NEWS]


async def test_a_duplicate_purpose_raises_the_port_error(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose())

    async def again() -> None:
        await _seed(uow, _purpose())

    with pytest.raises(PurposeExistsError):
        await again()


async def test_publishing_a_notice_makes_it_current(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose())
    async with uow() as unit:
        await unit.purposes.publish_notice(
            replace(
                _purpose(),
                notice_version=NoticeVersion("v2"),
                notice_published_at=EPOCH + timedelta(days=1),
            )
        )

    async with uow(read_only=True) as unit:
        found = await unit.purposes.get(ADS)
    assert found is not None
    assert (found.notice_version.value, found.notice_published_at) == (
        "v2",
        EPOCH + timedelta(days=1),
    )


async def test_the_ledger_keeps_recording_order_per_subject(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose(ADS), _purpose(NEWS))
    async with uow() as unit:
        await unit.ledger.append(_event("e1", purpose=ADS))
        await unit.ledger.append(_event("e2", subject=BOB))
        await unit.ledger.append(_event("e3", purpose=NEWS, minutes=1))
        # Same timestamp as e1: order still follows recording.
        await unit.ledger.append(_event("e4", purpose=ADS, decision=ConsentDecision.WITHDRAWN))

    async with uow(read_only=True) as unit:
        assert [e.id for e in await unit.ledger.history(ADA)] == ["e1", "e3", "e4"]
        assert (await unit.ledger.latest(ADA, ADS)) == _event(
            "e4", decision=ConsentDecision.WITHDRAWN
        )
        latest = await unit.ledger.latest_by_purpose(ADA)
        assert {p.value: e.id for p, e in latest.items()} == {"ads": "e4", "newsletter": "e3"}
        assert await unit.ledger.get("e2") == _event("e2", subject=BOB)
        assert await unit.ledger.get("missing") is None


async def test_appending_a_taken_event_id_raises(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose())
    async with uow() as unit:
        await unit.ledger.append(_event("e1"))

    async def again() -> None:
        async with uow() as unit:
            await unit.ledger.append(_event("e1", minutes=5))

    with pytest.raises(EventIdTakenError):
        await again()


async def test_an_error_discards_every_change(uow: ConsentUnitOfWorkFactory) -> None:
    async def failing_unit() -> None:
        async with uow() as unit:
            await unit.purposes.add(_purpose())
            await unit.ledger.append(_event("e1"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_unit()

    async with uow(read_only=True) as unit:
        assert await unit.purposes.all() == []
        assert await unit.ledger.history(ADA) == []


async def test_read_only_units_refuse_writes(uow: ConsentUnitOfWorkFactory) -> None:
    async def write_while_reading() -> None:
        async with uow(read_only=True) as unit:
            await unit.purposes.add(_purpose())

    with pytest.raises(ReadOnlyUnitOfWorkError):
        await write_while_reading()

    async with uow(read_only=True) as unit:
        assert await unit.purposes.all() == []


async def test_reporting_reads_aggregate_the_ledger(uow: ConsentUnitOfWorkFactory) -> None:
    await _seed(uow, _purpose(ADS), _purpose(NEWS))
    async with uow() as unit:
        await unit.ledger.append(_event("e1", purpose=ADS))
        await unit.ledger.append(_event("e2", purpose=ADS, decision=ConsentDecision.WITHDRAWN))
        await unit.ledger.append(_event("e3", subject=BOB, purpose=NEWS))

    async with uow(read_only=True) as unit:
        latest = {e.id for e in await unit.ledger.latest_decisions()}
        subjects = await unit.ledger.subject_count()
        tallies = {
            (t.decision.value, t.method, t.source): t.count for t in await unit.ledger.tallies()
        }

    assert latest == {"e2", "e3"}
    assert subjects == 2
    assert tallies == {
        ("granted", ConsentMethod.CHECKBOX, "web"): 2,
        ("withdrawn", None, "web"): 1,
    }
