from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    """Who triggered a use case, and through which request.

    Passed to use cases explicitly, so they run the same from HTTP, a CLI or a
    worker; the HTTP adapter builds it from blitz's request context.
    """

    #: The authenticated user, or ``None`` for anonymous calls (registration).
    user_id: str | None
    correlation_id: str
    client_address: str | None = None
    #: Where the call came from, e.g. ``"/v1/todos/"``.  Informational only.
    entrypoint: str | None = None
