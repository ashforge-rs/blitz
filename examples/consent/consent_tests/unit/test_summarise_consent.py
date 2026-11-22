from consent_app.entities import (
    ConsentMethod,
    ConsentState,
    NoticeVersion,
    Purpose,
    PurposeSlug,
    SubjectId,
)
from consent_app.profiles import GDPR
from consent_app.use_cases import GiveConsent, PublishNotice, SummariseConsent, WithdrawConsent
from consent_tests.fakes import FixedClock, InMemoryConsentUnitOfWorkFactory

from .conftest import NEWSLETTER, V1, V2


async def test_every_known_subject_is_counted_under_the_profile(
    give: GiveConsent,
    withdraw: WithdrawConsent,
    publish: PublishNotice,
    store: InMemoryConsentUnitOfWorkFactory,
    clock: FixedClock,
) -> None:
    ada, bob, cy, dee = (SubjectId(f"subj-{n}") for n in ("ada", "bob", "cy", "dee"))
    for subject in (ada, bob, cy):
        await give.execute(
            subject, NEWSLETTER, V1, ConsentMethod.CHECKBOX, source="web", recorded_by="crm"
        )
    await withdraw.execute(bob, NEWSLETTER, source="web", recorded_by="crm")
    await publish.execute(NEWSLETTER, V2)
    await give.execute(cy, NEWSLETTER, V2, ConsentMethod.TOGGLE, source="app", recorded_by="crm")
    await withdraw.execute(dee, PurposeSlug("newsletter"), source="web", recorded_by="crm")

    summary = (await SummariseConsent(store, GDPR, clock=clock).execute()).unwrap()

    newsletter = summary.purposes[NEWSLETTER]
    assert summary.subjects == 4
    assert newsletter.states == {
        ConsentState.RENEWAL_REQUIRED: 1,  # ada: granted under the old notice
        ConsentState.WITHDRAWN: 2,  # bob, dee
        ConsentState.GRANTED: 1,  # cy: renewed
    }
    assert newsletter.may_process == 1


async def test_subjects_who_never_decided_on_a_purpose_are_not_given(
    give: GiveConsent, store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock
) -> None:
    ads = PurposeSlug("ads")
    store.state.purposes[ads] = Purpose(ads, "Ads", NoticeVersion("v1"), clock.now(), clock.now())
    await give.execute(
        SubjectId("subj-ada"),
        NEWSLETTER,
        V1,
        ConsentMethod.CHECKBOX,
        source="web",
        recorded_by="crm",
    )

    summary = (await SummariseConsent(store, GDPR, clock=clock).execute()).unwrap()

    assert summary.purposes[ads].states == {ConsentState.NOT_GIVEN: 1}
    assert summary.purposes[ads].may_process == 0
