"""GiveConsent and WithdrawConsent on the in-memory store."""

from dataclasses import replace

import pytest
from returns.result import Result

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    ConsentState,
    NoticeVersion,
    PurposeSlug,
)
from consent_app.ports import StorageUnavailableError
from consent_app.use_cases import (
    ConsentError,
    ConsentErrorCode,
    ConsentRecorded,
    GiveConsent,
    WithdrawConsent,
)
from consent_tests.fakes import EPOCH, InMemoryConsentUnitOfWorkFactory
from consent_tests.fakes import ConsentState as StoreState

from .conftest import ADA, NEWSLETTER, V1, V2


async def grant(
    give: GiveConsent,
    *,
    method: ConsentMethod = ConsentMethod.CHECKBOX,
    notice: NoticeVersion = V1,
    purpose: PurposeSlug = NEWSLETTER,
    event_id: str | None = None,
) -> Result[ConsentRecorded, ConsentError]:
    return await give.execute(
        ADA, purpose, notice, method, source="web-signup", recorded_by="crm", event_id=event_id
    )


async def withdrawal(
    withdraw: WithdrawConsent, *, purpose: PurposeSlug = NEWSLETTER, event_id: str | None = None
) -> Result[ConsentRecorded, ConsentError]:
    return await withdraw.execute(
        ADA, purpose, source="support-call", recorded_by="callcentre", event_id=event_id
    )


async def test_a_grant_is_recorded_with_its_full_context(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    recorded = (await grant(give)).unwrap()

    [event] = store.state.events
    assert event == recorded.event
    assert (event.decision, event.notice_version, event.method) == (
        ConsentDecision.GRANTED,
        V1,
        ConsentMethod.CHECKBOX,
    )
    assert (event.source, event.recorded_by, event.profile, event.recorded_at) == (
        "web-signup",
        "crm",
        "gdpr",
        EPOCH,
    )
    assert (recorded.status.state, recorded.status.may_process) == (ConsentState.GRANTED, True)


async def test_a_passive_method_is_refused_before_touching_storage(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    store.fail_with = AssertionError("storage must not be touched")

    result = await grant(give, method=ConsentMethod.PRE_TICKED_BOX)

    assert result.failure().code is ConsentErrorCode.METHOD_NOT_ACCEPTED
    assert "checkbox" in result.failure().message


async def test_consent_to_an_outdated_notice_is_refused(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    store.state.purposes[NEWSLETTER] = replace(store.state.purposes[NEWSLETTER], notice_version=V2)

    result = await grant(give, notice=V1)

    assert result.failure().code is ConsentErrorCode.NOTICE_OUTDATED
    assert "2026-06" in result.failure().message
    assert store.state.events == []


async def test_an_unknown_purpose_is_refused(give: GiveConsent, withdraw: WithdrawConsent) -> None:
    unknown = PurposeSlug("unknown")

    assert (await grant(give, purpose=unknown)).failure().code is ConsentErrorCode.PURPOSE_NOT_FOUND
    assert (await withdrawal(withdraw, purpose=unknown)).failure().code is (
        ConsentErrorCode.PURPOSE_NOT_FOUND
    )


async def test_a_retry_with_the_same_event_id_records_nothing_new(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    first = (await grant(give, event_id="client-evt-1")).unwrap()
    retry = (await grant(give, event_id="client-evt-1")).unwrap()

    assert retry.replayed is True
    assert retry.event == first.event
    assert len(store.state.events) == 1


async def test_an_event_id_reused_for_another_decision_is_refused(
    give: GiveConsent, withdraw: WithdrawConsent
) -> None:
    await grant(give, event_id="client-evt-1")

    result = await withdrawal(withdraw, event_id="client-evt-1")

    assert result.failure().code is ConsentErrorCode.EVENT_ID_REUSED


async def test_a_lost_event_id_race_replays_the_winner(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    def concurrent_retry(state: StoreState, ours: ConsentEvent) -> None:
        state.events.append(ours)  # the same request, committed first by another worker

    store.concurrent_append = concurrent_retry

    recorded = (await grant(give, event_id="client-evt-1")).unwrap()

    assert recorded.replayed is True
    assert len(store.state.events) == 1


async def test_withdrawal_needs_no_method_and_ends_processing(
    give: GiveConsent, withdraw: WithdrawConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    await grant(give)

    recorded = (await withdrawal(withdraw)).unwrap()

    assert (recorded.event.method, recorded.event.notice_version) == (None, None)
    assert (recorded.status.state, recorded.status.may_process) == (ConsentState.WITHDRAWN, False)
    assert [e.decision for e in store.state.events] == [
        ConsentDecision.GRANTED,
        ConsentDecision.WITHDRAWN,
    ]


async def test_withdrawal_without_a_grant_is_still_recorded(
    withdraw: WithdrawConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    result = await withdrawal(withdraw)

    assert result.unwrap().status.state is ConsentState.WITHDRAWN
    assert len(store.state.events) == 1


async def test_a_storage_outage_is_a_safe_failure(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    store.fail_with = StorageUnavailableError("database is locked")

    result = await grant(give)

    assert result.failure().code is ConsentErrorCode.STORAGE_ERROR
    assert "locked" not in result.failure().message


async def test_a_bug_is_not_disguised_as_a_storage_error(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory
) -> None:
    store.fail_with = TypeError("bug")

    with pytest.raises(TypeError):
        await grant(give)
