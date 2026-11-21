# Todo app example

A small service built on the blitz boilerplate. Users register and get an API token, then
create todos with that token, over **HTTP or the command line**. Both drivers run the same use
cases on the same database: Postgres or SQLite, through SQLAlchemy and Alembic. Only create use
cases exist, on purpose: the example shows how to structure an app on blitz, not how to build a
full todo product.

The code follows **Clean Architecture**: business rules sit in framework-free `entities/` and
`use_cases/` packages, which define the interfaces (*ports*) they need, and *adapters*
implement them. Tests enforce the rules (see
[Enforced, not hoped for](docs/architecture.md#enforced-not-hoped-for)).

> **A reference implementation, not a production service.** The patterns are production-grade.
> The product isn't:
> - API tokens never expire and can't be revoked or scoped;
> - registration reveals whether an email exists (`409`);
> - SQLite is for local runs only;
> - with several instances, audit entries can be delivered twice (identified by `audit_id`).
>
> See [Known trade-offs](docs/design-decisions.md#known-trade-offs).

## Run

The example is its own uv project (own `pyproject.toml`, lock file and `.venv`), depending on
blitz from this repository. From `examples/todo/`:

```bash
make install        # uv sync
make dev            # HTTP API with hot reload on :8000
make verify         # format, lint, mypy --strict, tests (the root `make verify` runs it too)
```

SQLite is the default (`todo.db`). For Postgres:

```bash
make db-up          # docker compose: Postgres on :5432, plus a todo_test database
export TODO_DATABASE_URL=postgresql+asyncpg://todo:todo@localhost:5432/todo
make dev
TODO_TEST_POSTGRES_URL=postgresql+asyncpg://todo:todo@localhost:5432/todo_test make verify
```

Settings are read from the environment or `.env`. See [`.env.example`](.env.example) for this
app's `TODO_*` settings. The boilerplate's own settings (`PORT`, `ENVIRONMENT`, ...) still apply.

```bash
# 1. Register: the token is returned once and only its hash is stored.
curl -s -X POST localhost:8000/v1/users/ -H 'content-type: application/json' \
     -d '{"email": "ada@example.com", "name": "Ada"}'
# 201 {"user": {"id": "…", "email": "ada@example.com", …}, "api_token": "tdo_…"}

# 2. Create a todo as that user.
curl -s -X POST localhost:8000/v1/todos/ -H 'content-type: application/json' \
     -H 'Authorization: Bearer tdo_…' -d '{"title": "Buy milk"}'
# 201 {"id": "…", "owner_id": "<Ada's id>", "title": "Buy milk", "done": false, …}

curl -s localhost:8000/metrics | grep '^todoapp_'
```

| Request | Response |
| --- | --- |
| `POST /v1/users/` | `201` user + token · `409 email_taken` (case-insensitive) · `422` invalid body |
| `POST /v1/todos/` | `201` todo owned by the caller · `401` missing/unknown token · `422` blank title |
| either, storage down | `500 storage_error` (details logged, never sent) |
| either, with `Idempotency-Key` | a retry returns the original result (`Idempotent-Replayed: true`) · `422 idempotency_key_reused` if the body differs |

### Command line

The same use cases without a web stack ([Typer](https://typer.tiangolo.com); a test proves the
CLI never imports FastAPI):

```bash
uv run todo register --email ada@example.com --name Ada     # or: python -m todo_app.cli
# {"api_token": "tdo_…", "replayed": false, "user": {"id": "…", "email": "ada@example.com", …}}

export TODO_API_TOKEN=tdo_…      # never a flag: argv leaks into shell history and `ps`
uv run todo create-todo --title "Buy milk" --idempotency-key "$(uuidgen)"
# {"replayed": false, "todo": {"id": "…", "owner_id": "…", "title": "Buy milk", …}}
```

Results go to stdout as one JSON object, errors to stderr as `{"error": code, "message": …}`.
Exit codes follow `sysexits.h`:

| Exit | Meaning |
| --- | --- |
| `0` | success |
| `1` | refused by the use case (`email_taken`, `idempotency_key_reused`) |
| `2` | invalid input: the same value-object rules and messages as HTTP's `422` |
| `75` | storage unavailable. Retry with the same `--idempotency-key` |
| `77` | missing or invalid `TODO_API_TOKEN` |
| `78` | schema out of date: run `todo db upgrade` |

A token from one driver works in the other, and an idempotency key used in one replays in the
other (`todo_tests/cli/test_cli_http_interop.py`). The CLI doesn't poll the audit outbox: each
command delivers its entries when it closes. If the audit sink is down, the entries wait in the
outbox for the next process.

## Architecture

```mermaid
flowchart TB
    subgraph frameworks ["Frameworks and drivers"]
        direction LR
        fastapi["FastAPI + blitz<br/>create_app, ResultRouter, auth"]
        typer["Typer"]
        sqlite[("Postgres / SQLite<br/>SQLAlchemy + Alembic")]
        sinks["Prometheus · loguru · audit backend"]
    end
    subgraph adapters ["Interface adapters"]
        direction LR
        http["adapters/http/<br/>schemas · problems · routes"]
        cli["cli/<br/>commands · composition"]
        repos["adapters/sql_*<br/>units of work · repositories · migrations"]
        telemetry["adapters/observed_*_telemetry"]
        relay["persistence/outbox_relay"]
    end
    subgraph application ["Application"]
        direction LR
        usecases["use_cases/<br/>RegisterUser · AuthenticateToken · CreateTodo"]
        ports["ports/ + kernel ports<br/>abstract base classes"]
    end
    subgraph domain ["Domain"]
        entities["entities/<br/>User · EmailAddress · DisplayName · Todo · Title"]
    end

    fastapi --> http
    typer --> cli
    http --> usecases
    cli --> usecases
    usecases --> ports
    usecases --> entities
    ports --> entities
    repos -. implements .-> ports
    telemetry -. implements .-> ports
    repos --> sqlite
    telemetry --> sinks
    relay --> sinks
```

A solid arrow means *imports / calls*, and a dashed arrow means *subclasses the port*. Every
solid arrow between layers points inward, toward the domain. The use cases never import an
adapter. Instead the adapters implement the use cases' ports, and the composition root (below)
hands those implementations to the use cases. That is the dependency rule, and
`todo_tests/architecture/` fails the build if an import breaks it.

## Documentation

| Read | For |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Layout, ports and adapters, composition, request flow, enforced rules, the minimum viable version |
| [docs/design-decisions.md](docs/design-decisions.md) | Unit of work and outbox, idempotency, error rules, persistence, tokens, trade-offs |
| [docs/operations.md](docs/operations.md) | Settings, releasing schema changes, metrics, `/health`, dashboard, alerts |
| [ADR 0001](../../docs/adr/0001-layered-high-integrity-pattern.md) | When to use this pattern rather than blitz's flat domains |

## Test

```bash
make verify         # or just the tests: uv run pytest
```

The tests come in four tiers: unit, integration, fuzz and architecture. Each test that needs a
database gets a fresh SQLite file under `tmp_path`; storage tests also run on Postgres when
`TODO_TEST_POSTGRES_URL` is set (`make db-up` starts one; CI does it with a service container). `make verify` also formats, lints,
type-checks (`mypy --strict`, including that every fake satisfies its port) and tests this
example.
