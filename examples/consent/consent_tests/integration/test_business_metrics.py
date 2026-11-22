"""After seeding, the published gauges show exactly the seeded consent picture."""

from collections.abc import AsyncIterator, Callable

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

from consent_app.adapters.reporting import refresh
from consent_app.adapters.seed import PURPOSES, SUBJECTS, seed_demo_data
from consent_app.container import ConsentDomain, build_consent
from consent_app.settings import ConsentSettings


@pytest.fixture
async def seeded(database_url: str) -> AsyncIterator[ConsentDomain]:
    settings = ConsentSettings(_env_file=None, DATABASE_URL=SecretStr(database_url))  # type: ignore[call-arg]  # pydantic-settings init kwarg
    domain = await build_consent(settings)
    await seed_demo_data(domain, environment="development")
    yield domain
    await domain.aclose()


async def test_gauges_match_the_states_the_api_would_report(
    seeded: ConsentDomain, metric: Callable[..., float]
) -> None:
    assert await refresh(seeded.summarise)

    expected: dict[tuple[str, str], int] = {}
    for subject in SUBJECTS:
        for status in (await seeded.consent_status.execute(subject)).unwrap():
            key = (status.purpose.value, status.state.value)
            expected[key] = expected.get(key, 0) + 1
    for (purpose, state), count in expected.items():
        assert metric("consentapp_subjects", purpose=purpose, state=state) == count

    assert metric("consentapp_known_subjects") == len(SUBJECTS)
    assert (
        metric(
            "consentapp_purpose_notice_info", purpose="product_analytics", notice_version="2026-06"
        )
        == 1
    )
    assert len(PURPOSES) == 4


async def test_ledger_tallies_cover_every_recorded_event(
    seeded: ConsentDomain, metric: Callable[..., float]
) -> None:
    await refresh(seeded.summarise)
    history = 0
    for subject in SUBJECTS:
        history += len((await seeded.consent_history.execute(subject)).unwrap())

    total = sum(
        sample.value
        for family in REGISTRY.collect()
        if family.name == "consentapp_ledger_events"
        for sample in family.samples
    )
    assert total == history
