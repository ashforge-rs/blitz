class StorageUnavailableError(Exception):
    """Storage could not serve the request (locked, disk error, closed, ...).

    Adapters translate their driver's operational errors into this, so use
    cases can catch *infrastructure* failures without also swallowing bugs:
    any other exception is a defect and propagates.
    """


class ReadOnlyUnitOfWorkError(RuntimeError):
    """Something tried to write through a unit of work opened with ``read_only=True``: a bug."""
