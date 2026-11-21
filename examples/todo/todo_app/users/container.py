"""Composition root of the users context, independent of any delivery mechanism.

The only place that names the concrete classes (SQLite unit of work, outbox
relay, telemetry, system clock).  The HTTP app (``domain.py``) and the CLI
(``todo_app.cli``) both build the context through :func:`build_users`.
"""

from typing import TYPE_CHECKING

from todo_app.kernel import SystemClock, Uuid7Ids
from todo_app.persistence import Database, OutboxRelay

from .adapters.observed_user_telemetry import ObservedUserTelemetry
from .adapters.sqlite_users_unit_of_work import (
    MIGRATIONS,
    OUTBOX_TABLE,
    SqliteUsersUnitOfWorkFactory,
)
from .use_cases import AuthenticateToken, RegisterUser

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity

    from todo_app.settings import TodoSettings


class UsersDomain:
    """The users context's use cases and the resources they hold."""

    def __init__(
        self,
        *,
        register: RegisterUser,
        authenticate: AuthenticateToken,
        relay: OutboxRelay,
        db: Database,
    ) -> None:
        self.register = register
        self.authenticate = authenticate
        self.relay = relay
        self._db = db

    async def aclose(self) -> None:
        await self.relay.aclose()  # deliver what's pending before the connection goes
        await self._db.close()


async def build_users(
    settings: TodoSettings,
    *,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool = True,
) -> UsersDomain:
    """Open the users context.  ``poll_outbox=False`` (short-lived processes such as
    the CLI) delivers audit entries only when the context is closed."""
    db = await Database.connect(
        settings.DB_PATH, migrations=MIGRATIONS, busy_timeout_ms=settings.DB_BUSY_TIMEOUT_MS
    )
    uow = SqliteUsersUnitOfWorkFactory(db)
    telemetry = ObservedUserTelemetry()
    relay = OutboxRelay(
        db,
        OUTBOX_TABLE,
        audit_backend,
        audit_integrity,
        poll_interval=settings.OUTBOX_POLL_INTERVAL_SECONDS,
    )
    if poll_outbox:
        relay.start()
    return UsersDomain(
        register=RegisterUser(uow, telemetry, clock=SystemClock(), ids=Uuid7Ids()),
        authenticate=AuthenticateToken(uow, telemetry),
        relay=relay,
        db=db,
    )
