"""The CLI's composition root: both contexts, built exactly as the HTTP app builds them."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from audit.backends.loguru import LoguruAuditBackend
from audit.integrity import NoIntegrity
from todo_app.todos.container import TodosDomain, build_todos
from todo_app.users.container import UsersDomain, build_users

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from audit.backend import AuditBackend, AuditIntegrity
    from todo_app.settings import TodoSettings


@dataclass(frozen=True, slots=True)
class Services:
    users: UsersDomain
    todos: TodosDomain


@asynccontextmanager
async def open_services(
    settings: TodoSettings,
    *,
    audit_backend: AuditBackend | None = None,
    audit_integrity: AuditIntegrity | None = None,
) -> AsyncIterator[Services]:
    """Open both contexts for one command; closing delivers their audit outboxes."""
    backend = audit_backend or LoguruAuditBackend()
    integrity = audit_integrity or NoIntegrity()
    # A one-shot process doesn't poll: the outbox is flushed when each context closes.
    users = await build_users(
        settings, audit_backend=backend, audit_integrity=integrity, poll_outbox=False
    )
    try:
        todos = await build_todos(
            settings, audit_backend=backend, audit_integrity=integrity, poll_outbox=False
        )
        try:
            yield Services(users=users, todos=todos)
        finally:
            await todos.aclose()
    finally:
        await users.aclose()
