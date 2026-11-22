"""Demo data for local development: three users and their todos.

Loaded through the use cases, like real traffic: values are validated, every
change is audited, and the Idempotency-Keys make a re-run (within the 24 h replay
window) record nothing twice.  Refuses to run in production.
"""

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from returns.pipeline import is_successful

from todo_app.kernel import Actor
from todo_app.todos.entities import Title
from todo_app.users.entities import DisplayName, EmailAddress
from todo_app.users.use_cases import UserErrorCode

if TYPE_CHECKING:
    from .composition import Services

#: (email, display name, todo titles).  example.com is reserved for documentation (RFC 2606).
DEMO_USERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "ada@example.com",
        "Ada Lovelace",
        ("Review the analytical engine notes", "Write up Bernoulli numbers", "Reply to Babbage"),
    ),
    (
        "grace@example.com",
        "Grace Hopper",
        (
            "Prepare COBOL workshop",
            "Find the moth in relay 70",
            "Order nanosecond wire samples",
            "Plan the fleet audit",
        ),
    ),
    (
        "alan@example.com",
        "Alan Turing",
        ("Draft the imitation game paper", "Run the morphogenesis model"),
    ),
)


class SeedingRefusedError(RuntimeError):
    """Demo data must never reach a production database."""


@dataclass
class SeededUser:
    email: str
    user_id: str
    #: Fresh on every run: a replayed registration rotates the token.
    api_token: str
    todos: list[str] = field(default_factory=list)


@dataclass
class SeedReport:
    users: list[SeededUser] = field(default_factory=list)
    #: Demo users already registered by a run older than the 24 h replay window: their
    #: tokens can't be reissued and their todos are left alone (no duplicates).
    existing: list[str] = field(default_factory=list)
    #: True when every record already existed.
    replayed: bool = True


async def seed_demo_data(services: Services, *, environment: str) -> SeedReport:
    if environment == "production":
        msg = "refusing to load demo data with ENVIRONMENT=production"
        raise SeedingRefusedError(msg)

    report = SeedReport()
    for email, name, titles in DEMO_USERS:
        slug = email.split("@", 1)[0]
        registered = await services.users.register.execute(
            EmailAddress(email),
            DisplayName(name),
            _actor(),
            idempotency_key=f"demo-seed-user-{slug}",
        )
        if not is_successful(registered):
            error = registered.failure()
            if error.code is UserErrorCode.EMAIL_TAKEN:
                report.existing.append(email)
                continue
            msg = f"could not seed {email}: {error.code.value} ({error.message})"
            raise SeedingRefusedError(msg)
        registration = registered.unwrap()
        report.replayed &= registration.replayed
        seeded = SeededUser(email, registration.user.id, registration.api_token)

        for n, title in enumerate(titles, start=1):
            created = await services.todos.create.execute(
                registration.user.id,
                Title(title),
                _actor(registration.user.id),
                idempotency_key=f"demo-seed-todo-{slug}-{n}",
            )
            todo = created.unwrap()  # a seed failure is a bug: let it surface
            report.replayed &= todo.replayed
            seeded.todos.append(todo.todo.id)
        report.users.append(seeded)
    return report


def _actor(user_id: str | None = None) -> Actor:
    return Actor(user_id=user_id, correlation_id=uuid.uuid4().hex, entrypoint="cli:seed")
