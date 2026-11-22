"""Composition root: the only place that names concrete classes."""

from typing import TYPE_CHECKING

from .adapters.reporting import Reporter
from .adapters.sql import schema
from .adapters.sql.database import Database
from .adapters.sql.unit_of_work import SqlConsentUnitOfWorkFactory
from .adapters.system import SystemClock, Uuid7Ids
from .use_cases import (
    CreatePurpose,
    GetConsentHistory,
    GetConsentStatus,
    GiveConsent,
    ListPurposes,
    PublishNotice,
    SummariseConsent,
    WithdrawConsent,
)

if TYPE_CHECKING:
    from .settings import ConsentSettings


class ConsentDomain:
    """The consent use cases and the database behind them."""

    def __init__(self, db: Database, settings: ConsentSettings) -> None:
        uow = SqlConsentUnitOfWorkFactory(db)
        profile = settings.profile
        clock, ids = SystemClock(), Uuid7Ids()
        self.create_purpose = CreatePurpose(uow, clock=clock)
        self.list_purposes = ListPurposes(uow)
        self.publish_notice = PublishNotice(uow, clock=clock)
        self.give_consent = GiveConsent(uow, profile, clock=clock, ids=ids)
        self.withdraw_consent = WithdrawConsent(uow, profile, clock=clock, ids=ids)
        self.consent_status = GetConsentStatus(uow, profile, clock=clock)
        self.consent_history = GetConsentHistory(uow)
        self.summarise = SummariseConsent(uow, profile, clock=clock)
        self.profile = profile
        self.db = db
        self._reporter: Reporter | None = None

    def start_reporting(self, interval_s: float) -> None:
        """Publish business metrics periodically (long-running processes only)."""
        self._reporter = Reporter(self.summarise, interval_s)
        self._reporter.start()

    async def aclose(self) -> None:
        if self._reporter is not None:
            await self._reporter.aclose()
        await self.db.close()


async def build_consent(settings: ConsentSettings) -> ConsentDomain:
    db = await Database.connect(
        settings.DATABASE_URL.get_secret_value(),
        connect_timeout_s=settings.DB_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        if settings.DB_MIGRATE_ON_STARTUP:
            await schema.upgrade(db)
        else:
            await schema.ensure_at_head(db)
    except BaseException:
        await db.close()
        raise
    return ConsentDomain(db, settings)
