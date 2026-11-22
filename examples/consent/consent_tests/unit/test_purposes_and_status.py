"""Purposes, notice changes, and the status and history clients read."""

from consent_app.entities import ConsentMethod, ConsentState, NoticeVersion, PurposeSlug, SubjectId
from consent_app.use_cases import (
    ConsentErrorCode,
    CreatePurpose,
    GetConsentHistory,
    GetConsentStatus,
    GiveConsent,
    PublishNotice,
    WithdrawConsent,
)
from consent_tests.fakes import EPOCH, FixedClock, InMemoryConsentUnitOfWorkFactory

from .conftest import ADA, NEWSLETTER, V1, V2


async def test_creating_a_purpose_records_its_first_notice(
    create_purpose: CreatePurpose, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    ads = PurposeSlug("ads")

    purpose = (await create_purpose.execute(ads, "Personalised ads", V1)).unwrap()

    assert (purpose.notice_version, purpose.created_at) == (V1, EPOCH)
    assert (ads, V1.value) in store.state.notices


async def test_a_duplicate_purpose_is_refused(create_purpose: CreatePurpose) -> None:
    result = await create_purpose.execute(NEWSLETTER, "Again", V1)

    assert result.failure().code is ConsentErrorCode.PURPOSE_EXISTS


async def test_publishing_a_notice_keeps_the_history_and_requires_renewal(
    give: GiveConsent,
    publish: PublishNotice,
    status: GetConsentStatus,
    store: InMemoryConsentUnitOfWorkFactory,
    clock: FixedClock,
) -> None:
    await give.execute(ADA, NEWSLETTER, V1, ConsentMethod.CHECKBOX, source="web", recorded_by="crm")
    clock.advance(days=30)

    purpose = (await publish.execute(NEWSLETTER, V2)).unwrap()
    [after] = (await status.execute(ADA, NEWSLETTER)).unwrap()

    assert (purpose.notice_version, purpose.notice_published_at) == (V2, clock.now())
    assert [v for s, v in store.state.notices if s == NEWSLETTER] == [V1.value, V2.value]
    assert (after.state, after.may_process) == (ConsentState.RENEWAL_REQUIRED, False)


async def test_republishing_the_current_notice_is_refused(publish: PublishNotice) -> None:
    result = await publish.execute(NEWSLETTER, V1)

    assert result.failure().code is ConsentErrorCode.NOTICE_UNCHANGED


async def test_publishing_for_an_unknown_purpose_is_refused(publish: PublishNotice) -> None:
    result = await publish.execute(PurposeSlug("unknown"), NoticeVersion("v9"))

    assert result.failure().code is ConsentErrorCode.PURPOSE_NOT_FOUND


async def test_status_covers_every_purpose_and_defaults_to_no_processing(
    create_purpose: CreatePurpose, give: GiveConsent, status: GetConsentStatus
) -> None:
    await create_purpose.execute(PurposeSlug("ads"), "Personalised ads", V1)
    await give.execute(ADA, NEWSLETTER, V1, ConsentMethod.TOGGLE, source="app", recorded_by="crm")

    statuses = {s.purpose.value: s for s in (await status.execute(ADA)).unwrap()}

    assert statuses["newsletter"].may_process is True
    assert (statuses["ads"].state, statuses["ads"].may_process) == (ConsentState.NOT_GIVEN, False)


async def test_status_for_an_unknown_purpose_is_refused(status: GetConsentStatus) -> None:
    result = await status.execute(ADA, PurposeSlug("unknown"))

    assert result.failure().code is ConsentErrorCode.PURPOSE_NOT_FOUND


async def test_history_is_every_decision_oldest_first_and_per_subject(
    give: GiveConsent, withdraw: WithdrawConsent, history: GetConsentHistory
) -> None:
    bob = SubjectId("subj-bob")
    await give.execute(ADA, NEWSLETTER, V1, ConsentMethod.CHECKBOX, source="web", recorded_by="crm")
    await give.execute(bob, NEWSLETTER, V1, ConsentMethod.CHECKBOX, source="web", recorded_by="crm")
    await withdraw.execute(ADA, NEWSLETTER, source="email-link", recorded_by="crm")

    events = (await history.execute(ADA)).unwrap()

    assert [(e.subject, e.decision.value, e.source) for e in events] == [
        (ADA, "granted", "web"),
        (ADA, "withdrawn", "email-link"),
    ]
