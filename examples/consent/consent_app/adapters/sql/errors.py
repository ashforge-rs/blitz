"""Outages become ``StorageUnavailableError``; bugs and constraint violations propagate.

Decided by result code, not exception class: SQLite reports a syntax error and a
locked database with the same class, and so does Postgres for a dropped
connection and a bad query.
"""

import contextlib
from typing import TYPE_CHECKING

from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from consent_app.ports import StorageUnavailableError

if TYPE_CHECKING:
    from collections.abc import Iterator

_SQLITE = ("SQLITE_BUSY", "SQLITE_LOCKED", "SQLITE_IOERR", "SQLITE_FULL", "SQLITE_CANTOPEN")
# Connection exceptions, insufficient resources, shutdown, lock/statement timeouts,
# serialization failures and deadlocks; and a misconfigured database (bad credentials
# 28xxx, missing database 3D000): unusable until an operator fixes it, so not a bug.
_POSTGRES = ("08", "53", "57P", "55P03", "40001", "40P01", "57014", "28", "3D000")


def _code(exc: DBAPIError) -> str:
    for source in (exc.orig, getattr(exc.orig, "__cause__", None)):
        for attr in ("sqlite_errorname", "sqlstate", "pgcode"):
            value = getattr(source, attr, None)
            if isinstance(value, str) and value:
                return value
    return ""


def is_unavailable(exc: BaseException) -> bool:
    if isinstance(exc, PoolTimeoutError | ConnectionError | TimeoutError):
        return True
    if isinstance(exc, DBAPIError):
        code = _code(exc)
        return exc.connection_invalidated or code.startswith(_SQLITE) or code.startswith(_POSTGRES)
    return False


@contextlib.contextmanager
def translate_storage_errors() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        if is_unavailable(exc):
            message = str(exc) or f"could not reach the database ({type(exc).__name__})"
            raise StorageUnavailableError(message) from exc
        raise
