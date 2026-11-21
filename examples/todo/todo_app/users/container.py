"""Composition root of the users context, independent of any delivery mechanism.

The only place that names the users context's concrete classes.  The HTTP app
(``domain.py``) and the CLI (``todo_app.cli``) both build it through :func:`build_users`.
"""

from typing import TYPE_CHECKING

from todo_app.kernel import SystemClock, Uuid7Ids
from todo_app.persistence import open_context_runtime

from .adapters.observed_user_telemetry import ObservedUserTelemetry
from .adapters.sql_migrations import MIGRATIONS
from .adapters.sql_tables import audit_outbox, idempotency
from .adapters.sql_users_unit_of_work import SqlUsersUnitOfWorkFactory
from .use_cases import AuthenticateToken, RegisterUser

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity

    from todo_app.persistence import ContextRuntime, OutboxRelay
    from todo_app.settings import TodoSettings


class UsersDomain:
    """The users context's use cases and the runtime (database, audit relay) behind them."""

    def __init__(
        self, *, register: RegisterUser, authenticate: AuthenticateToken, runtime: ContextRuntime
    ) -> None:
        self.register = register
        self.authenticate = authenticate
        self._runtime = runtime

    @property
    def relay(self) -> OutboxRelay:
        return self._runtime.relay

    async def health(self, *, max_outbox_age_s: float) -> dict[str, object]:
        return await self._runtime.health(max_outbox_age_s=max_outbox_age_s)

    async def aclose(self) -> None:
        await self._runtime.aclose()


async def build_users(
    settings: TodoSettings,
    *,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool = True,
) -> UsersDomain:
    runtime = await open_context_runtime(
        "users",
        settings,
        migrations=MIGRATIONS,
        outbox=audit_outbox,
        idempotency=idempotency,
        audit_backend=audit_backend,
        audit_integrity=audit_integrity,
        poll_outbox=poll_outbox,
    )
    uow = SqlUsersUnitOfWorkFactory(runtime.db)
    telemetry = ObservedUserTelemetry()
    clock, ids = SystemClock(), Uuid7Ids()
    return UsersDomain(
        register=RegisterUser(uow, telemetry, clock=clock, ids=ids),
        authenticate=AuthenticateToken(uow, telemetry),
        runtime=runtime,
    )
