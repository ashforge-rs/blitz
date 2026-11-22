"""Use cases wired to the in-memory store, a fixed clock and sequential ids, under GDPR."""

import pytest

from consent_app.entities import NoticeVersion, Purpose, PurposeSlug, SubjectId
from consent_app.profiles import GDPR
from consent_app.use_cases import (
    CreatePurpose,
    GetConsentHistory,
    GetConsentStatus,
    GiveConsent,
    PublishNotice,
    WithdrawConsent,
)
from consent_tests.fakes import EPOCH, FixedClock, InMemoryConsentUnitOfWorkFactory, SequentialIds

ADA = SubjectId("subj-ada")
NEWSLETTER = PurposeSlug("newsletter")
V1, V2 = NoticeVersion("2026-01"), NoticeVersion("2026-06")


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def store() -> InMemoryConsentUnitOfWorkFactory:
    store = InMemoryConsentUnitOfWorkFactory()
    # As CreatePurpose would leave it: the purpose and its first notice.
    store.state.purposes[NEWSLETTER] = Purpose(NEWSLETTER, "Monthly newsletter", V1, EPOCH, EPOCH)
    store.state.notices.append((NEWSLETTER, V1.value))
    return store


@pytest.fixture
def give(store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock) -> GiveConsent:
    return GiveConsent(store, GDPR, clock=clock, ids=SequentialIds())


@pytest.fixture
def withdraw(store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock) -> WithdrawConsent:
    return WithdrawConsent(store, GDPR, clock=clock, ids=SequentialIds("wd"))


@pytest.fixture
def status(store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock) -> GetConsentStatus:
    return GetConsentStatus(store, GDPR, clock=clock)


@pytest.fixture
def history(store: InMemoryConsentUnitOfWorkFactory) -> GetConsentHistory:
    return GetConsentHistory(store)


@pytest.fixture
def create_purpose(store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock) -> CreatePurpose:
    return CreatePurpose(store, clock=clock)


@pytest.fixture
def publish(store: InMemoryConsentUnitOfWorkFactory, clock: FixedClock) -> PublishNotice:
    return PublishNotice(store, clock=clock)
