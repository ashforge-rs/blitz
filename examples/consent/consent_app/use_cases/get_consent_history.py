from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import ConsentEvent, SubjectId
    from consent_app.ports import ConsentUnitOfWorkFactory


class GetConsentHistory:
    """Every decision a subject made: the evidence that consent was given (GDPR Art. 7(1))."""

    def __init__(self, uow: ConsentUnitOfWorkFactory) -> None:
        self._uow = uow

    async def execute(self, subject: SubjectId) -> Result[list[ConsentEvent], ConsentError]:
        try:
            async with self._uow(read_only=True) as uow:
                return Success(await uow.ledger.history(subject))
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
