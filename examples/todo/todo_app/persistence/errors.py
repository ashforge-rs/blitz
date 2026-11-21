"""Translate driver errors: outages become ``StorageUnavailableError``; bugs propagate.

Decided by result code, never by exception class alone: SQLite reports a syntax
error and a locked database with the same class, and so does Postgres for a
dropped connection and a bad query.
"""

import contextlib
from typing import TYPE_CHECKING

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from todo_app.kernel import StorageUnavailableError

if TYPE_CHECKING:
    from collections.abc import Iterator

#: SQLite result codes (with extended variants, e.g. SQLITE_IOERR_WRITE) meaning
#: "can't serve this right now".
_SQLITE_UNAVAILABLE = (
    "SQLITE_BUSY",
    "SQLITE_LOCKED",
    "SQLITE_IOERR",
    "SQLITE_FULL",
    "SQLITE_CANTOPEN",
    "SQLITE_READONLY",
    "SQLITE_CORRUPT",
    "SQLITE_NOTADB",
    "SQLITE_PROTOCOL",
    "SQLITE_NOMEM",
    "SQLITE_INTERRUPT",
)
#: Postgres SQLSTATEs (prefixes) meaning the same: connection exceptions,
#: insufficient resources, operator intervention / shutdown, lock timeouts,
#: serialization failures and deadlocks (both safe to retry), statement timeouts.
_POSTGRES_UNAVAILABLE = ("08", "53", "57P", "55P03", "40001", "40P01", "57014")


def _code(exc: DBAPIError) -> str:
    orig = exc.orig
    for source in (orig, getattr(orig, "__cause__", None)):
        for attr in ("sqlite_errorname", "sqlstate", "pgcode"):
            value = getattr(source, attr, None)
            if isinstance(value, str) and value:
                return value
    return ""


def is_unavailable(exc: BaseException) -> bool:
    if isinstance(exc, PoolTimeoutError | ConnectionError | TimeoutError):
        return True
    if isinstance(exc, DBAPIError):
        if exc.connection_invalidated:
            return True
        code = _code(exc)
        return code.startswith(_SQLITE_UNAVAILABLE) or code.startswith(_POSTGRES_UNAVAILABLE)
    return False


@contextlib.contextmanager
def translate_storage_errors() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        if is_unavailable(exc):
            raise StorageUnavailableError(str(exc)) from exc
        raise


def violates_unique(exc: IntegrityError, *, constraint: str, sqlite_columns: str) -> bool:
    """Whether ``exc`` is the unique violation of ``constraint``.

    Postgres names the constraint; SQLite names the columns ("users.email").
    """
    cause = getattr(exc.orig, "__cause__", None)
    if getattr(cause, "constraint_name", None) == constraint:
        return True
    message = str(exc.orig)
    return constraint in message or f"UNIQUE constraint failed: {sqlite_columns}" in message
