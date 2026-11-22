"""Errors that are part of the ports' contracts: adapters raise them, use cases catch them."""


class StorageUnavailableError(Exception):
    """Storage could not serve the request (locked, unreachable, disk error, ...).

    Adapters translate their driver's *operational* errors into this, so use cases
    can catch outages without also swallowing bugs: anything else propagates.
    """


class ReadOnlyUnitOfWorkError(RuntimeError):
    """Something tried to write through a unit of work opened with ``read_only=True``: a bug."""


class PurposeExistsError(Exception):
    """:meth:`PurposeRepository.add`: a purpose with this slug already exists."""


class EventIdTakenError(Exception):
    """:meth:`ConsentLedger.append`: an event with this id was recorded concurrently."""
