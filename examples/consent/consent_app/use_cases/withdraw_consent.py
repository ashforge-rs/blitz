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
    from consent_app.entities import PurposeSlug, SubjectId
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory, IdGenerator
    from consent_app.profiles import RegulationProfile


class WithdrawConsent:
    """Record that a subject withdrew consent for a purpose.

    Always accepted, with no method requirement: withdrawing must be as easy as
    giving (GDPR Art. 7(3)).  Withdrawing without an earlier grant is recorded too:
    an explicit refusal is worth keeping.
    """

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
        *,
        source: str,
        recorded_by: str,
        event_id: str | None = None,
    ) -> Result[ConsentRecorded, ConsentError]:
        event = ConsentEvent(
            id=event_id or self._ids.new_id(),
            subject=subject,
            purpose=purpose,
            decision=ConsentDecision.WITHDRAWN,
            notice_version=None,
            method=None,
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
                await uow.ledger.append(event)
                return ConsentRecorded(event, self._profile.status(found, event, event.recorded_at))

        try:
            return Success(await retry_once_on_id_race(attempt))
        except Refusal as refusal:
            return Failure(refusal.error)
        except EventIdReusedError:
            return Failure(consent_error(ConsentErrorCode.EVENT_ID_REUSED))
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
