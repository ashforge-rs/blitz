"""The consent rules: GDPR's, and the core's neutrality towards any regulation."""

from datetime import timedelta

import pytest

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    ConsentState,
    NoticeVersion,
    Purpose,
    PurposeSlug,
    SubjectId,
)
from consent_app.profiles import GDPR, PROFILES, ConsentModel, RegulationProfile
from consent_tests.fakes import EPOCH

ADS = PurposeSlug("ads")
V1, V2 = NoticeVersion("v1"), NoticeVersion("v2")
PURPOSE = Purpose(ADS, "Personalised ads", V1, EPOCH, EPOCH)


def _event(
    decision: ConsentDecision, notice: NoticeVersion | None = V1, days: int = 0
) -> ConsentEvent:
    granted = decision is ConsentDecision.GRANTED
    return ConsentEvent(
        id="e1",
        subject=SubjectId("s1"),
        purpose=ADS,
        decision=decision,
        notice_version=notice if granted else None,
        method=ConsentMethod.CHECKBOX if granted else None,
        source="web",
        recorded_by="crm",
        profile="any",
        recorded_at=EPOCH + timedelta(days=days),
    )


def test_gdpr_is_registered() -> None:
    assert PROFILES["gdpr"] is GDPR


def test_gdpr_never_asked_means_no_processing() -> None:
    status = GDPR.status(PURPOSE, None, EPOCH)

    assert (status.state, status.may_process) == (ConsentState.NOT_GIVEN, False)


def test_gdpr_a_grant_allows_processing_until_withdrawn() -> None:
    granted = GDPR.status(PURPOSE, _event(ConsentDecision.GRANTED), EPOCH + timedelta(days=3650))
    withdrawn = GDPR.status(PURPOSE, _event(ConsentDecision.WITHDRAWN), EPOCH)

    assert (granted.state, granted.may_process) == (ConsentState.GRANTED, True)
    assert (withdrawn.state, withdrawn.may_process) == (ConsentState.WITHDRAWN, False)


def test_gdpr_a_changed_notice_requires_renewal() -> None:
    changed = Purpose(ADS, "Personalised ads", V2, EPOCH, EPOCH)

    status = GDPR.status(changed, _event(ConsentDecision.GRANTED, notice=V1), EPOCH)

    assert (status.state, status.may_process) == (ConsentState.RENEWAL_REQUIRED, False)


@pytest.mark.parametrize(
    "method", [ConsentMethod.PRE_TICKED_BOX, ConsentMethod.IMPLIED, ConsentMethod.INACTIVITY]
)
def test_gdpr_rejects_passive_methods(method: ConsentMethod) -> None:
    assert not GDPR.accepts(method)


def test_gdpr_accepts_affirmative_methods() -> None:
    assert all(GDPR.accepts(m) for m in (ConsentMethod.CHECKBOX, ConsentMethod.DOUBLE_OPT_IN))


# The core knows no regulation: these synthetic profiles exercise the other rules.

OPT_OUT = RegulationProfile(
    name="opt_out_example",
    model=ConsentModel.OPT_OUT,
    accepted_methods=frozenset(ConsentMethod),
    max_validity=None,
    renew_on_notice_change=False,
)
EXPIRING = RegulationProfile(
    name="expiring_example",
    model=ConsentModel.OPT_IN,
    accepted_methods=frozenset({ConsentMethod.CHECKBOX}),
    max_validity=timedelta(days=395),
    renew_on_notice_change=False,
)


def test_an_opt_out_regime_allows_processing_until_the_subject_objects() -> None:
    assert OPT_OUT.status(PURPOSE, None, EPOCH).may_process is True
    assert OPT_OUT.status(PURPOSE, _event(ConsentDecision.WITHDRAWN), EPOCH).may_process is False


def test_a_profile_without_renewal_ignores_notice_changes() -> None:
    changed = Purpose(ADS, "Personalised ads", V2, EPOCH, EPOCH)

    assert (
        OPT_OUT.status(changed, _event(ConsentDecision.GRANTED), EPOCH).state
        is ConsentState.GRANTED
    )


def test_a_validity_period_expires_grants_exactly_at_its_end() -> None:
    grant = _event(ConsentDecision.GRANTED)

    just_before = EXPIRING.status(
        PURPOSE, grant, EPOCH + timedelta(days=395) - timedelta(seconds=1)
    )
    at_the_end = EXPIRING.status(PURPOSE, grant, EPOCH + timedelta(days=395))

    assert just_before.state is ConsentState.GRANTED
    assert (at_the_end.state, at_the_end.may_process) == (ConsentState.EXPIRED, False)
