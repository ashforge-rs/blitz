"""Demo data for local development: purposes, and a realistic spread of decisions.

``python -m consent_app.adapters.seed`` (or ``make seed``).  Everything goes through
the use cases, so the profile's rules apply: a demo pre-ticked box is refused like a
real one.  Event ids are fixed, so a re-run replays instead of recording twice.
Refuses to run in production.
"""

import asyncio
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import get_settings
from returns.pipeline import is_successful

from consent_app.container import ConsentDomain, build_consent
from consent_app.entities import ConsentMethod, NoticeVersion, PurposeSlug, SubjectId
from consent_app.ports import StorageUnavailableError
from consent_app.settings import ConsentSettings
from consent_app.use_cases import ConsentErrorCode

if TYPE_CHECKING:
    from returns.result import Result

    from consent_app.use_cases import ConsentError, ConsentRecorded

FIRST_NOTICE = NoticeVersion("2026-01")
#: product_analytics gets a new notice mid-way: earlier grants then need renewal.
REVISED_NOTICE = NoticeVersion("2026-06")
ANALYTICS = PurposeSlug("product_analytics")
PURPOSES: tuple[tuple[PurposeSlug, str], ...] = (
    (PurposeSlug("newsletter"), "Monthly product newsletter by email"),
    (ANALYTICS, "Usage analytics to improve the product"),
    (PurposeSlug("personalised_ads"), "Ads tailored to your activity on our sites"),
    (PurposeSlug("partner_sharing"), "Sharing contact details with selected partners"),
)
#: channel → the client system that records it.
CHANNELS: tuple[tuple[str, str], ...] = (
    ("web-signup", "demo-web"),
    ("mobile-app", "demo-app"),
    ("email-preferences", "demo-web"),
    ("support-call", "demo-callcentre"),
)
SUBJECTS = tuple(SubjectId(f"subj-demo-{n:03d}") for n in range(1, 25))


class SeedingRefusedError(RuntimeError):
    """Demo data must never reach a production database."""


@dataclass
class SeedReport:
    purposes_created: int = 0
    recorded: int = 0
    replayed: int = 0
    refused: Counter[str] = field(default_factory=Counter)
    states: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, object]:
        return {
            "purposes_created": self.purposes_created,
            "subjects": len(SUBJECTS),
            "events_recorded": self.recorded,
            "events_replayed": self.replayed,
            "refused": dict(self.refused),
            "states": dict(sorted(self.states.items())),
        }

    def count(self, result: Result[ConsentRecorded, ConsentError]) -> None:
        if is_successful(result):
            if result.unwrap().replayed:
                self.replayed += 1
            else:
                self.recorded += 1
            return
        code = result.failure().code
        if code is ConsentErrorCode.STORAGE_ERROR:
            msg = "storage unavailable while seeding"
            raise SeedingRefusedError(msg)
        self.refused[code.value] += 1


async def seed_demo_data(domain: ConsentDomain, *, environment: str) -> SeedReport:
    if environment == "production":
        msg = "refusing to load demo data with ENVIRONMENT=production"
        raise SeedingRefusedError(msg)
    report = SeedReport()
    rng = random.Random(2026)  # noqa: S311 — reproducible demo data, not security
    methods = sorted(domain.profile.accepted_methods)

    def meta(subject: SubjectId, purpose: PurposeSlug, step: str) -> dict[str, str]:
        source, client = rng.choice(CHANNELS)
        return {
            "source": source,
            "recorded_by": client,
            "event_id": f"demo-{subject.value}-{purpose.value}-{step}",
        }

    for slug, description in PURPOSES:
        if is_successful(await domain.create_purpose.execute(slug, description, FIRST_NOTICE)):
            report.purposes_created += 1

    for subject in SUBJECTS:
        for slug, _ in PURPOSES:
            if rng.random() < 0.7:  # most subjects decide on most purposes
                grant = domain.give_consent.execute(
                    subject, slug, FIRST_NOTICE, rng.choice(methods), **meta(subject, slug, "grant")
                )
                report.count(await grant)
                if rng.random() < 0.25:
                    withdrawal = domain.withdraw_consent.execute(
                        subject, slug, **meta(subject, slug, "withdraw")
                    )
                    report.count(await withdrawal)

    # The analytics notice changes; every second subject agrees to the new one.
    await domain.publish_notice.execute(ANALYTICS, REVISED_NOTICE)
    for subject in SUBJECTS[::2]:
        regrant = domain.give_consent.execute(
            subject,
            ANALYTICS,
            REVISED_NOTICE,
            rng.choice(methods),
            **meta(subject, ANALYTICS, "regrant"),
        )
        report.count(await regrant)

    # A pre-ticked box is not consent: the profile refuses it, and nothing is stored.
    sharing = PurposeSlug("partner_sharing")
    pre_ticked = domain.give_consent.execute(
        SUBJECTS[0],
        sharing,
        FIRST_NOTICE,
        ConsentMethod.PRE_TICKED_BOX,
        **meta(SUBJECTS[0], sharing, "pre-ticked"),
    )
    report.count(await pre_ticked)

    for subject in SUBJECTS:
        for status in (await domain.consent_status.execute(subject)).unwrap():
            report.states[status.state.value] += 1
    return report


async def _main() -> None:
    domain = await build_consent(ConsentSettings())
    try:
        report = await seed_demo_data(domain, environment=get_settings().ENVIRONMENT)
    finally:
        await domain.aclose()
    print(json.dumps(report.as_dict(), indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except SeedingRefusedError as exc:
        sys.exit(f"seed refused: {exc}")
    except StorageUnavailableError as exc:
        # e.g. Postgres not started, wrong port or credentials, missing database.
        sys.exit(f"seed failed, the database is unavailable: {exc}")
