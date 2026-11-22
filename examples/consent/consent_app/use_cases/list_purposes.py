from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import Purpose
    from consent_app.ports import ConsentUnitOfWorkFactory


class ListPurposes:
    def __init__(self, uow: ConsentUnitOfWorkFactory) -> None:
        self._uow = uow

    async def execute(self) -> Result[list[Purpose], ConsentError]:
        try:
            async with self._uow(read_only=True) as uow:
                return Success(await uow.purposes.all())
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
