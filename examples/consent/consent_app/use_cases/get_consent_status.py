from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import ConsentStatus, PurposeSlug, SubjectId
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory
    from consent_app.profiles import RegulationProfile


class GetConsentStatus:
    """May the controller process the subject's data for a purpose?  (Or for every purpose.)

    This is what client systems ask before processing; the answer follows the
    deployment's profile, so it accounts for expiry and notice changes.
    """

    def __init__(
        self, uow: ConsentUnitOfWorkFactory, profile: RegulationProfile, *, clock: Clock
    ) -> None:
        self._uow = uow
        self._profile = profile
        self._clock = clock

    async def execute(
        self, subject: SubjectId, purpose: PurposeSlug | None = None
    ) -> Result[list[ConsentStatus], ConsentError]:
        try:
            async with self._uow(read_only=True) as uow:
                if purpose is None:
                    purposes = await uow.purposes.all()
                else:
                    found = await uow.purposes.get(purpose)
                    if found is None:
                        return Failure(consent_error(ConsentErrorCode.PURPOSE_NOT_FOUND))
                    purposes = [found]
                latest = await uow.ledger.latest_by_purpose(subject)
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
        now = self._clock.now()
        return Success([self._profile.status(p, latest.get(p.slug), now) for p in purposes])
