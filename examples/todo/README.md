# Todo app example

A small service built on the blitz boilerplate. Users register and get an API token, then
create todos with that token, over **HTTP or the command line**. Both drivers run the same use
cases on the same database. It stores everything with SQLAlchemy and Alembic, on Postgres or SQLite, and exposes Prometheus counters.
Only create use cases exist, on purpose: the example shows how to structure an app on blitz,
not how to build a full todo product.

The code follows **Clean Architecture**: business rules sit in framework-free `entities/` and
`use_cases/` packages, which define the interfaces (*ports*) they need, and *adapters* implement them. A test
enforces the dependency rule (see [Enforced, not hoped for](#enforced-not-hoped-for)).

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


Every layer is a package. Each module inside holds one concept and is named after it, and the
package's `__init__.py` exports the public names (`from todo_app.users.entities import User`).

```
examples/todo/
├── pyproject.toml                       # own project: blitz (by path) + typer, tool config
├── Makefile                             # install · dev · verify · fmt · test · coverage
├── .env.example
├── conftest.py                          # fixtures: app/client on a temp DB, audit_log, db, metric
├── todo_app/
│   ├── kernel/                          # shared kernel (stdlib only)
│   │   ├── actor.py                     # Actor: who called, which request
│   │   ├── audit.py                     # AuditRecord, AuditTrail port
│   │   ├── idempotency.py               # IdempotencyRecord, IdempotencyStore port, TTL
│   │   ├── errors.py                    # StorageUnavailableError
│   │   ├── clock.py                     # Clock port, SystemClock
│   │   └── ids.py                       # IdGenerator port, Uuid7Ids
│   ├── persistence/                     # shared SQL infrastructure (SQLAlchemy Core, async)
│   │   ├── database.py                  # Database: engine, transaction(), dialect setup
│   │   ├── errors.py                    # outage vs bug, by SQLite code / Postgres SQLSTATE
│   │   ├── tables.py  types.py          # outbox + idempotency table builders, UtcDateTime
│   │   ├── sql_audit_outbox.py          # AuditTrail inside the transaction
│   │   ├── sql_idempotency_store.py     # IdempotencyStore inside the transaction
│   │   ├── migrations.py                # upgrade(), ensure_at_head() via Alembic
│   │   └── outbox_relay.py              # delivers committed audit entries to the backend
│   ├── web/                             # shared HTTP helpers: request_actor, Idempotency-Key
│   ├── auth/
│   │   ├── principal.py                 # Principal
│   │   ├── token_verifier.py            # TokenVerifier port
│   │   ├── bearer_token_provider.py     # BearerTokenAuthProvider (blitz AuthProvider)
│   │   └── dependencies.py              # CurrentPrincipalDep
│   ├── settings.py                      # TodoSettings (TODO_*), handed to bootstraps
│   ├── factory.py                       # HTTP composition root: create_todo_app()
│   ├── main.py  __main__.py             # ASGI app / python -m todo_app
│   ├── cli/                             # command-line driver (Typer), no web imports
│   │   ├── main.py                      # create_cli(): Typer app, logging (audit always on)
│   │   ├── commands.py                  # args → value objects → use case → JSON + exit code
│   │   ├── composition.py               # open_services(): both containers, outbox drained on exit
│   │   └── exit_codes.py                # sysexits-style ExitCode
│   ├── users/
│   │   ├── entities/
│   │   │   ├── user.py                  # User
│   │   │   ├── email_address.py         # EmailAddress (normalising value object)
│   │   │   ├── display_name.py          # DisplayName
│   │   │   └── api_token.py             # generate / hash / pre-check API tokens
│   │   ├── ports/
│   │   │   ├── unit_of_work.py          # UsersUnitOfWork (+ factory): the atomic boundary
│   │   │   ├── user_repository.py       # UserRepository, EmailTakenError
│   │   │   ├── api_token_repository.py  # ApiTokenRepository
│   │   │   └── user_telemetry.py        # UserTelemetry: metrics/logs, must not raise
│   │   ├── use_cases/
│   │   │   ├── register_user.py         # RegisterUser, Registration (+ idempotent replay)
│   │   │   ├── authenticate_token.py    # AuthenticateToken
│   │   │   └── errors.py                # UserErrorCode, UserError (no HTTP status)
│   │   ├── adapters/
│   │   │   ├── http/
│   │   │   │   ├── schemas.py           # Pydantic request/response bodies
│   │   │   │   ├── problems.py          # UserProblem: error → HTTP status
│   │   │   │   └── routes.py            # POST /users/
│   │   │   ├── sql_tables.py                  # the context's tables (SQLAlchemy Core)
│   │   │   ├── sql_users_unit_of_work.py      # one database transaction
│   │   │   ├── sql_user_repository.py
│   │   │   ├── sql_api_token_repository.py
│   │   │   ├── sql_migrations.py              # upgrade() / ensure_at_head() for this context
│   │   │   ├── migrations/                    # Alembic env + versions, table alembic_version_users
│   │   │   ├── observed_user_telemetry.py     # Prometheus counters, logs
│   │   │   └── users_token_verifier.py        # AuthenticateToken → auth.TokenVerifier
│   │   ├── container.py                 # UsersDomain + build_users(): framework-free wiring
│   │   └── domain.py                    # blitz domain module: make_router(), bootstrap()
│   └── todos/                           # same shape: entities/{todo,title}.py,
│                                        # ports/{unit_of_work,todo_repository,todo_telemetry}.py,
│                                        # use_cases/{create_todo,errors}.py, adapters/...
└── todo_tests/
    ├── fakes/                           # transactional in-memory units of work, telemetry
    │                                    # recorders, FixedClock, SequentialIds, RecordingAuditBackend
    ├── fixture_types.py                 # types of the conftest fixtures
    ├── unit/                            # one file per use case / entity module, on fakes
    ├── integration/                     # Database, outbox relay, unit-of-work *contract* tests
    │                                    # (fakes, SQLite and Postgres alike), migrations, HTTP, audit, metrics, wiring
    ├── cli/                             # CLI commands, CLI+HTTP interop, runtime import proof
    ├── fuzz/                            # Hypothesis properties of value objects and tokens
    └── architecture/                    # the dependency rule, as a test
```

### Ports and adapters

Each port is an abstract base class owned by the application layer. Production adapters
(`Sql*`, `Observed*`) and test fakes (`InMemory*`, `*Recorder`) subclass it, so they can
be swapped without the use case noticing. The users context looks like this, and todos has the
same shape:

```mermaid
classDiagram
    direction LR
    class RegisterUser {
        +execute(email, name, actor, idempotency_key) Result
    }
    class UsersUnitOfWorkFactory {
        <<abstract>>
        +create(read_only) UsersUnitOfWork
    }
    class UsersUnitOfWork {
        <<abstract>>
        +users UserRepository
        +api_tokens ApiTokenRepository
        +audit AuditTrail
        +idempotency IdempotencyStore
    }
    class UserRepository {
        <<abstract>>
        +add(user)
        +get(user_id)
        +find_by_token_hash(token_hash)
    }
    class UserTelemetry {
        <<abstract>>
        +registered(user, actor, replayed)
        +registration_rejected(reason, actor)
        +storage_failed(operation, error, actor)
    }
    RegisterUser --> UsersUnitOfWorkFactory : opens units of work
    RegisterUser --> UserTelemetry : reports after commit
    UsersUnitOfWorkFactory ..> UsersUnitOfWork : creates
    UsersUnitOfWork --> UserRepository : exposes
    UsersUnitOfWorkFactory <|-- SqlUsersUnitOfWorkFactory
    UsersUnitOfWorkFactory <|-- InMemoryUsersUnitOfWorkFactory
    UsersUnitOfWork <|-- SqlUsersUnitOfWork
    UsersUnitOfWork <|-- InMemoryUsersUnitOfWork
    UserRepository <|-- SqlUserRepository
    UserRepository <|-- InMemoryUserRepository
    UserTelemetry <|-- ObservedUserTelemetry
    UserTelemetry <|-- UserTelemetryRecorder
```

(The factory's `create` is its `__call__`: `async with factory() as uow:`.)

### Composition: two drivers, one wiring

The only code that names concrete classes is each context's `container.py`. The HTTP app and
the CLI are two thin composition roots on top of it, so both get identical use cases:

```mermaid
flowchart LR
    containers["users/container.py · todos/container.py<br/>build_users() · build_todos()"]
    concrete["Database · Sql*UnitOfWorkFactory<br/>Observed*Telemetry · OutboxRelay<br/>SystemClock · Uuid7Ids"]
    usecases["RegisterUser · AuthenticateToken · CreateTodo"]

    subgraph httpproc ["HTTP process"]
        factory["factory.py<br/>create_todo_app()"] --> lifespan["blitz create_app()<br/>lifespan calls bootstrap()"]
        lifespan --> domainmods["users/domain.py · todos/domain.py"]
    end
    subgraph cliproc ["CLI process"]
        climain["cli/main.py<br/>create_cli()"] --> opensvc["cli/composition.py<br/>open_services()"]
    end

    domainmods --> containers
    opensvc --> containers
    containers -- builds --> concrete
    containers -- injects them into --> usecases
```

The HTTP process starts the outbox relay as a background task. The CLI doesn't poll; it drains
the outbox when each command closes.

### How a request flows

`POST /v1/todos/` with a bearer token and an `Idempotency-Key`:

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant B as blitz auth
    participant V as UsersTokenVerifier
    participant R as todos HTTP route
    participant U as CreateTodo
    participant D as Database
    participant T as TodoTelemetry
    participant O as OutboxRelay
    participant S as Audit backend

    C->>B: POST /v1/todos/ with Bearer token and Idempotency-Key
    B->>V: verify(token, actor)
    V->>D: AuthenticateToken: read-only unit of work
    V-->>B: user id
    B->>R: Principal(user_id)
    R->>U: execute(owner_id, Title, actor, key)
    rect rgba(80, 140, 255, 0.12)
        Note over U,D: one unit of work = one database transaction
        U->>D: BEGIN, look up the idempotency key
        alt same key and body seen before
            D-->>U: original todo (replay)
        else new request
            U->>D: insert todo
            U->>D: insert audit entry (outbox row)
            U->>D: insert idempotency record
        end
        U->>D: COMMIT
    end
    U->>T: created(todo, replayed), after the commit, never raises
    U-->>R: Success(TodoCreated)
    R-->>C: 201 TodoResponse, plus Idempotent-Replayed on a replay
    Note over O,S: later, in the background
    O->>D: read committed outbox rows, oldest first
    O->>S: log(AuditEvent)
    O->>D: delete the delivered row
```

1. **blitz auth**: `BearerTokenAuthProvider` asks its `TokenVerifier` port. The composition
   root plugged in the users context's `UsersTokenVerifier`, which runs `AuthenticateToken`.
   The route receives a `Principal(user_id)`.
2. **HTTP adapter** (`todos/adapters/http/routes.py`): Pydantic validates the body, delegating
   to the `Title` value object. The adapter builds an `Actor` (user, request ID, client, path)
   from blitz's request context and calls `CreateTodo.execute(owner_id, Title(...), actor,
   idempotency_key=...)`.
3. **Use case** (`todos/use_cases/create_todo.py`): opens one **unit of work**, which is a single
   database transaction. Inside it the use case:
   - looks up the idempotency key, and if it's a retry returns the original todo;
   - adds the todo;
   - records the audit entry in the **outbox**;
   - stores the idempotency record.

   Everything commits together or not at all. Only after the commit does it report to
   `TodoTelemetry`, which handles metrics and logs and never raises.
4. **Outbox relay** (`persistence/outbox_relay.py`): a background task delivers committed audit
   entries to blitz's audit backend, oldest first, and deletes each one only once the backend
   has accepted it.
5. **Back out**: the HTTP adapter maps `TodoCreated → TodoResponse` (setting
   `Idempotent-Replayed` on a replay) and `TodoError → TodoProblem`, and blitz's `ResultRouter`
   renders the result.

### Principles, and where each one lives

| Principle | In this code |
| --- | --- |
| Dependency rule | `entities/` imports only the stdlib and `kernel/`. `ports/` and `use_cases/` add `returns` and their own context's inner packages. Adapters import inward, never the reverse. |
| Entities hold business rules | `EmailAddress` normalises and validates itself, as do `DisplayName` and `Title`. An invalid `User` can't be constructed. |
| Use cases are application-specific rules | `RegisterUser`, `AuthenticateToken` and `CreateTodo` are plain classes with explicit dependencies. |
| Ports owned by the application | Every port is an abstract base class (`abc.ABC` + `@abstractmethod`). `ports/` defines the units of work, repositories and telemetry. `kernel/` defines `Clock`, `IdGenerator`, `AuditTrail` and `IdempotencyStore`, and `auth/` defines `TokenVerifier`. `EmailTakenError` is part of the port's contract, not SQLite's. |
| Adapters implement ports explicitly | Every adapter and every fake subclasses its port (`class SqlUserRepository(UserRepository)`), so an incomplete one fails on instantiation, and your editor can list each port's implementations. |
| Framework independence | No FastAPI, Pydantic, SQLite, Prometheus, loguru or blitz types in `entities/`, `ports/` or `use_cases/`. HTTP statuses live in `adapters/http/problems.py`. |
| Separate input/output models | Pydantic `RegisterUserBody` / `RegisteredUserResponse` exist only at the HTTP edge, so the API shape can change without touching entities. |
| Bounded contexts | `users` and `todos` never import each other, and todos keep the owner as a bare id with no foreign key. Only `factory.py` sees both. |
| Composition root | Each context's `container.py` is the only place it names concrete classes. `factory.py` (HTTP) and `cli/composition.py` (CLI) build both contexts from those containers. |
| Independent of delivery | The CLI drives the same use cases with no FastAPI in the process: `-X importtime` checks this at runtime, and the architecture test checks it statically. |
| Unit of work | `ports/unit_of_work.py` is the atomic boundary. A use case's writes, including its audit entry and idempotency record, commit together. |
| Explicit inputs | Use cases receive an `Actor` value, never blitz's `RequestContext`, so they run the same from HTTP, a CLI or a worker. |
| Testability | Use cases are tested against transactional in-memory fakes with a fixed clock and sequential IDs, with no I/O. Contract tests run the same checks against the fakes and SQLite. |

### Enforced, not hoped for

`todo_tests/architecture/test_dependency_rule.py` parses every import, including relative ones
resolved to full module names, and fails the build if any of these happen:
- an entity imports anything other than the stdlib (minus I/O and driver modules such as
  `sqlite3` and `asyncio`), `kernel/` or its own package;
- a port or use case reaches outside its context's `entities/`, `ports/` and `use_cases/`;
- one context imports the other;
- `auth/` imports a context.

`todo_tests/architecture/test_ports_and_adapters.py` discovers every port and fails if one isn't
an abstract base class, or if it lacks a concrete subclass in `todo_app` or a fake in
`todo_tests/fakes`. Use-case ports need a fake; `TokenVerifier` is exercised through HTTP only.

### Where this deviates from blitz's domain contract, and why

AGENTS.md describes a flatter layout (`models.py`, `service.py`, ...). This example keeps
blitz's *runtime* contract: each context's `domain.py` exposes `make_router()` and `bootstrap()`,
domains are looked up with `get_domain()`, `aclose()` releases resources, errors become RFC 9457
problems through `ResultRouter`, and state changes are audited. It changes four conventions so
the inner layers stay framework-free and side effects stay consistent:

- **Use cases take an `Actor`, not `ctx: RequestContext`.** `RequestContext` wraps the
  Starlette request. The HTTP adapter turns it into a plain `Actor` (`web/actor.py`).
- **Audit goes through an outbox, not `log_operation`.** Entries are written in the use case's
  transaction and delivered by `OutboxRelay`, so an audit outage can't fail or undo a change.
- **Use-case errors carry no HTTP status.** `UserProblem` / `TodoProblem` (subclasses of
  `DomainError`, in `adapters/http/problems.py`) add the status.
- **Entities are dataclasses, not Pydantic models.** Pydantic schemas are adapter code.

## Design notes

### Consistency: unit of work + transactional outbox

A use case's writes (entities, audit entry, idempotency record) share one transaction, and
side effects that can't join it come strictly afterwards:

| Side effect | When | If it fails |
| --- | --- | --- |
| Audit entry | In the transaction, as an outbox row | The whole change rolls back. Nothing is half-done. |
| Delivery to the audit backend | Later, by `OutboxRelay` | The entry stays in the outbox and is retried. The request is unaffected. |
| Metrics and logs | After the commit, through the telemetry port | Swallowed and logged. The port's contract says it must not raise. |

Delivery is at least once. A crash right after the backend accepted an entry can repeat it, and
`metadata["audit_id"]` identifies the duplicate. A refused request (`email_taken`, a reused
key) rolls back and is then audited in its own small unit of work.

`todo_tests/integration/test_audit.py::test_audit_outage_neither_fails_nor_loses_a_registration`
is the regression test. Before this design, an audit failure returned `500` *after* the commit:
the account existed but its token was lost.

### Idempotency: safe retries

POST endpoints accept an `Idempotency-Key` header: a random value, 8–255 printable characters.
- **Retrying with the same key and body within 24 hours** returns the original result with
  `Idempotent-Replayed: true`. The same key with a different body is refused with `422`.
- **Keys are scoped:** todos per owner, so one user's key can never replay another user's todo.
- **The record is written in the same transaction as the change,** so a request that times out
  after committing (for example a 504 from blitz's timeout middleware) is safe to retry.

```mermaid
sequenceDiagram
    actor C as Client
    participant U as RegisterUser
    participant D as Database

    C->>U: register ada with key K
    U->>D: user + token hash H1 + audit entry + record K maps to user, H1
    D-->>U: COMMIT
    U--xC: 201 with token T1, but the response is lost (timeout, network)
    C->>U: retry: register ada with key K
    U->>D: key K found, same request fingerprint
    U->>D: revoke H1, add H2, update record, audit entry marked replayed
    D-->>U: COMMIT
    U-->>C: 201 with the same user, token T2, Idempotent-Replayed true
    Note over C,D: exactly one token from this registration works: T2
```

Registration can't return the original token on a retry, because only its hash was stored. A
retried registration therefore issues a fresh token and revokes the undelivered one, so
exactly one token from that registration is valid. The key works like a short-lived secret:
generate it randomly (a UUIDv4) and never reuse it.

### Error rules: outages vs bugs

```mermaid
flowchart TD
    raised["An exception reaches the use case"] --> outage{"StorageUnavailableError?<br/>SQLite BUSY, LOCKED, IOERR · Postgres 08xxx, 53xxx, 40001 ..."}
    outage -- yes --> storage["Failure STORAGE_ERROR<br/>safe message, telemetry.storage_failed"]
    storage --> http500s["HTTP 500, code storage_error"]
    storage --> cli75["CLI exit 75: retry"]
    outage -- no --> known{"A port error?<br/>EmailTakenError, IdempotencyConflictError"}
    known -- yes --> rejected["rolled back, refusal audited<br/>Failure EMAIL_TAKEN or KEY_REUSED"]
    rejected --> http4xx["HTTP 409 or 422"]
    rejected --> cli1["CLI exit 1"]
    known -- no --> bug["A bug: propagates unchanged<br/>never counted as a storage error"]
    bug --> http500["HTTP plain 500, sanitised in production"]
    bug --> clitb["CLI traceback, non-zero exit"]
```

- **Outages.** `persistence/errors.py` translates the codes that mean "can't serve this right
  now" into `StorageUnavailableError`: SQLite *result codes* (BUSY, LOCKED, IOERR, FULL, ...),
  Postgres *SQLSTATEs* (connection exceptions `08`, resources `53`, shutdown `57P`, lock and
  statement timeouts, serialization failures and deadlocks), and connect or pool timeouts.
  That `StorageUnavailableError`, which is the only exception
  use cases catch (→ `500 storage_error`).
- **Constraint violations** propagate to the repository, which translates the ones it knows
  (`EmailTakenError`).
- **Bugs.** Everything else, including SQL syntax errors and a `TypeError` in an adapter,
  propagates to blitz's unhandled-error handler as a plain 500. It is never counted or audited as
  "storage". Tests cover each path.
- **Messages.** Use-case error messages are fixed, safe strings. Raw driver text goes to logs
  only, never into responses or audit entries.

### Persistence: SQLAlchemy, Alembic, Postgres or SQLite

- **SQLAlchemy Core (async)**, not the ORM: the repositories map rows to the framework-free
  entities explicitly. Swapping the database is a matter of `TODO_DATABASE_URL`, and the
  contract tests run on both.
- **`Database.transaction()`** is one database transaction on its own pooled connection,
  committed when the block completes and rolled back when it raises or is cancelled (blitz's
  request timeout). Read-only units of work always end in `ROLLBACK`; on Postgres they are also
  `READ ONLY`.
- **SQLite:** writes take the write lock up front (`BEGIN IMMEDIATE`), so two connections can't
  deadlock upgrading read locks. Connections use WAL mode and foreign keys.
- **Postgres:** `pool_pre_ping` replaces connections the server dropped, and
  `TODO_DB_CONNECT_TIMEOUT_SECONDS` bounds every connection attempt and pool wait, so an
  unreachable database fails fast instead of hanging each request.
- **Timestamps** are stored in UTC and always read back timezone-aware (`UtcDateTime`).
- **Migrations:** each context has its own Alembic environment and version table
  (`alembic_version_users`, `alembic_version_todos`), so they evolve independently.
  - **Startup:** with `TODO_DB_MIGRATE_ON_STARTUP=true` (development) the app migrates itself.
    In production, set it to false and run `todo db upgrade` as a release step. Startup then
    refuses to run against a schema that isn't at head (CLI exit `78`).
  - **New revision:** `uv run alembic -c todo_app/users/adapters/migrations/alembic.ini revision
    --autogenerate -m "…"`.
  - **Drift test:** `todo_tests/integration/test_migrations.py` fails if the migrations and
    `sql_tables.py` drift apart, and checks that every history downgrades and upgrades cleanly.

### API tokens

- 256 random bits with a `tdo_` prefix, so secret scanners can recognise leaked tokens.
- Stored as a SHA-256 hash in their own table, so a user can hold several.
- A fast hash is safe because tokens are high-entropy, unlike passwords.
- Emails and tokens never appear in logs, audit entries or `422` details (tests assert this).
- A storage outage during authentication returns `500`, never `401`.

### One file, a connection per context

Each context opens and closes its own `Database` and owns its own tables, outbox and idempotency
store, so either context could move to its own database. `aclose()` drains its outbox before
closing the connection.

## Known trade-offs

- **Account enumeration.** `409 email_taken` on the public registration endpoint reveals
  whether an email is registered, and only the global rate limit slows probing. The real fix is
  an email-verification flow (always `202`, details sent by email), which is beyond a
  create-only example.
- **Storage outages aren't audited.** The outbox is in the storage that failed. They are logged
  and counted (`todoapp_users_storage_failures_total`, `todoapp_todos_created_total{result="error"}`).
- **Integrity sequence gaps.** `SequenceIntegrity` numbers events as they're delivered, so an
  entry whose delivery failed gets a new number when it's retried.
- **SQLite is for local runs.** Writes are serialised, and with `WORKERS > 1` processes contend
  for the file lock: a write that can't get it within `TODO_DB_BUSY_TIMEOUT_MS` becomes a
  `storage_error`. Use Postgres anywhere else.
- **Several app instances relay the same outbox** without claiming rows, so an entry can be
  delivered twice (identified by `audit_id`). `FOR UPDATE SKIP LOCKED` claiming is the next step.
- **Housekeeping.** Expired idempotency records are overwritten when their key is reused, but
  never purged.

## Monitoring

| Metric | Labels |
| --- | --- |
| `todoapp_users_registered_total` | `result`: `success`, `replayed`, `email_taken`, `idempotency_key_reused`, `error` |
| `todoapp_users_storage_failures_total` | `operation`: `users.register`, `users.authenticate` |
| `todoapp_todos_created_total` | `result`: `success`, `replayed`, `idempotency_key_reused`, `error` |
| `todoapp_auth_attempts_total` | `result`: `success`, `missing`, `invalid`, `error` |
| `todoapp_audit_outbox_pending` (gauge) | `outbox`: entries committed but not yet delivered |
| `todoapp_audit_outbox_oldest_age_seconds` (gauge) | `outbox`: age of the oldest undelivered entry |
| `todoapp_audit_delivered_total` / `_delivery_failures_total` | `outbox` |

- **`/health`** reports each context (`users`, `todos`): whether its database answers, how many
  audit entries are pending, and the age of the oldest. It returns **503** when a database is
  down or an entry has waited longer than `TODO_OUTBOX_MAX_AGE_SECONDS` (default 300 s), so a
  stuck relay takes the instance out of rotation instead of silently losing the audit trail's
  freshness.
- **Dashboard:** [`grafana/todo-dashboard.json`](grafana/todo-dashboard.json). It has blitz's HTTP
  overview plus rows for users and auth, todos, and the audit outbox. Import it via Grafana →
  Dashboards → Import, or drop it into the repository's `grafana/provisioning/dashboards/`.
- **Alerts:** [`grafana/alerts.yml`](grafana/alerts.yml), as Prometheus rules:

  | Alert | Fires when | Severity |
  | --- | --- | --- |
  | `AuditOutboxStale` | oldest audit entry is over 300 s old for 5 min | critical |
  | `AuditDeliveryFailing` | every delivery attempt fails for 10 min | warning |
  | `StorageUnavailable` | use cases fail with `storage_error` for 5 min | critical |
  | `InvalidTokenSpike` | more than 20 % of auth attempts (and over 1/s) use unknown tokens | warning |

  `todo_tests/integration/test_monitoring_assets.py` fails if either file queries a metric the
  app doesn't export.

## Test

```bash
make verify         # or just the tests: uv run pytest
```

The tests come in four tiers: unit, integration, fuzz and architecture. Each test that needs a
database gets a fresh SQLite file under `tmp_path`; storage tests also run on Postgres when
`TODO_TEST_POSTGRES_URL` is set (`make db-up` starts one; CI does it with a service container). `make verify` also formats, lints,
type-checks (`mypy --strict`, including that every fake satisfies its port) and tests this
example.
