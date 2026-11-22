"""Business metrics: the stored consent picture, published as Prometheus gauges.

Refreshed periodically by the HTTP app from the database, so data written by
any process (the API, ``make seed``, another instance) shows up on dashboards.
"""

import asyncio
import contextlib
from typing import TYPE_CHECKING

from loguru import logger
from prometheus_client import Gauge
from returns.pipeline import is_successful

if TYPE_CHECKING:
    from consent_app.use_cases import ConsentSummary, SummariseConsent

SUBJECTS = Gauge(
    "consentapp_subjects", "Known subjects by purpose and consent state", ["purpose", "state"]
)
PROCESSABLE = Gauge(
    "consentapp_subjects_may_process",
    "Subjects whose data may be processed, by purpose",
    ["purpose"],
)
KNOWN_SUBJECTS = Gauge("consentapp_known_subjects", "Distinct subjects in the ledger")
LEDGER_EVENTS = Gauge(
    "consentapp_ledger_events",
    "Ledger events by decision, method and source",
    ["decision", "method", "source"],
)
NOTICE = Gauge(
    "consentapp_purpose_notice_info",
    "The current notice version of each purpose (always 1)",
    ["purpose", "notice_version"],
)


def publish(summary: ConsentSummary) -> None:
    for gauge in (SUBJECTS, PROCESSABLE, LEDGER_EVENTS, NOTICE):
        gauge.clear()  # drop label sets that no longer exist (e.g. a retired notice version)
    KNOWN_SUBJECTS.set(summary.subjects)
    for slug, purpose in summary.purposes.items():
        for state, count in purpose.states.items():
            SUBJECTS.labels(purpose=slug.value, state=state.value).set(count)
        PROCESSABLE.labels(purpose=slug.value).set(purpose.may_process)
        NOTICE.labels(purpose=slug.value, notice_version=purpose.purpose.notice_version.value).set(
            1
        )
    for tally in summary.tallies:
        method = tally.method.value if tally.method else "none"
        LEDGER_EVENTS.labels(decision=tally.decision.value, method=method, source=tally.source).set(
            tally.count
        )


async def refresh(summarise: SummariseConsent) -> bool:
    result = await summarise.execute()
    if is_successful(result):
        publish(result.unwrap())
        return True
    logger.warning("consent.reporting.refresh_failed", error=result.failure().message)
    return False


class Reporter:
    """Refreshes the business metrics every ``interval_s`` until closed."""

    def __init__(self, summarise: SummariseConsent, interval_s: float) -> None:
        self._summarise = summarise
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="consent-reporting")

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while True:
            try:
                await refresh(self._summarise)
            except Exception as exc:  # noqa: BLE001 — a background task must not die
                logger.error("consent.reporting.error", error=str(exc))
            await asyncio.sleep(self._interval_s)
