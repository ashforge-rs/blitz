"""Todo app: an example service built on the blitz boilerplate.

Each bounded context (``users/``, ``todos/``) is layered the same way::

    entities/    enterprise rules: self-validating dataclasses (stdlib only)
    use_cases/   application rules, one module per use case, + their errors
    ports/       interfaces the use cases need, one module per port
    adapters/    implementations: http/, sql_* (SQLAlchemy + Alembic migrations/), observed_*
    domain.py    composition root + blitz domain module (make_router, bootstrap)

Shared modules::

    kernel/      Clock, IdGenerator: abstractions the inner layers may use
    auth/        bearer-token AuthProvider, its TokenVerifier port, Principal
    persistence/ Database (SQLAlchemy async engine), outbox, idempotency, relay, migrations
    settings.py  TodoSettings (TODO_* environment variables)
    factory.py   create_todo_app(): the composition root that sees every context
    main.py      the ASGI ``app`` (uvicorn todo_app.main:app)
"""
