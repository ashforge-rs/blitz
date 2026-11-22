from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.entities import ConsentDecision, ConsentEvent
from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error
from .recording import (
    ConsentRecorded,
    EventIdReusedError,
    Refusal,
    find_replay,
    retry_once_on_id_race,
)

if TYPE_CHECKING:
    from consent_app.entities import ConsentMethod, NoticeVersion, PurposeSlug, SubjectId
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory, IdGenerator
    from consent_app.profiles import RegulationProfile


class GiveConsent:
    """Record that a subject granted consent for a purpose, if the profile accepts how."""

    def __init__(
        self,
        uow: ConsentUnitOfWorkFactory,
        profile: RegulationProfile,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow
        self._profile = profile
        self._clock = clock
        self._ids = ids

    async def execute(
        self,
        subject: SubjectId,
        purpose: PurposeSlug,
        notice_version: NoticeVersion,
        method: ConsentMethod,
        *,
        source: str,
        recorded_by: str,
        event_id: str | None = None,
    ) -> Result[ConsentRecorded, ConsentError]:
        if not self._profile.accepts(method):
            accepted = ", ".join(sorted(self._profile.accepted_methods))
            return Failure(
                consent_error(ConsentErrorCode.METHOD_NOT_ACCEPTED, f"accepted: {accepted}")
            )
        event = ConsentEvent(
            id=event_id or self._ids.new_id(),
            subject=subject,
            purpose=purpose,
            decision=ConsentDecision.GRANTED,
            notice_version=notice_version,
            method=method,
            source=source,
            recorded_by=recorded_by,
            profile=self._profile.name,
            recorded_at=self._clock.now(),
        )

        async def attempt() -> ConsentRecorded:
            async with self._uow() as uow:
                found = await uow.purposes.get(purpose)
                if found is None:
                    raise Refusal(consent_error(ConsentErrorCode.PURPOSE_NOT_FOUND))
                if (earlier := await find_replay(uow.ledger, event)) is not None:
                    status = self._profile.status(found, earlier, self._clock.now())
                    return ConsentRecorded(earlier, status, replayed=True)
                if notice_version != found.notice_version:
                    detail = f"current: {found.notice_version.value}"
                    raise Refusal(consent_error(ConsentErrorCode.NOTICE_OUTDATED, detail))
                await uow.ledger.append(event)
                return ConsentRecorded(event, self._profile.status(found, event, event.recorded_at))

        try:
            return Success(await retry_once_on_id_race(attempt))
        except Refusal as refused:
            return Failure(refused.error)
        except EventIdReusedError:
            return Failure(consent_error(ConsentErrorCode.EVENT_ID_REUSED))
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
