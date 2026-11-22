# blitz CLI

`blitz` generates code from predefined templates and manages the project's boilerplate:
domains, endpoints, services, extension points and integrations. It is its own uv project
(own lock and `.venv`), so neither typer nor the templates end up in the service images.

```bash
uv run --project cli blitz --help      # from the repository root (or `make cli ARGS=--help`)
```

The project root is the nearest directory above the current one with `pyproject.toml` and
`src/services/` (`--root` overrides it). Nothing is ever overwritten: a generator that would
replace a file stops before writing, and every generator takes `--dry-run`. Generated and
edited Python is import-sorted and formatted with the project's Ruff config.

## Generators: `blitz generate` / `blitz g`

| Generator (alias) | Creates | Wires |
| --- | --- | --- |
| `domain` (`d`) `<name> [--entity E] [-f field:type ...] [--no-crud]` | `src/domains/<name>/` + unit / integration / fuzz tests | the service's `DOMAINS` |
| `resource` (`res`, `crud`) `[Entity] [-f ...]` | the same, entity-first; **asks** for whatever is missing | the service's `DOMAINS` |
| `service` (`s`) `<name>` | `src/services/<name>/`: `main.py`, empty `domains.py`, `Dockerfile` | — |
| `endpoint` (`e`) `<domain> <name> [--method post] [--collection]` | a service method stub, its route and an integration test | the domain's router |
| `error-code` (`ec`) `<domain> <code> [--status 409]` | an `<Entity>ErrorCode` member | its HTTP status in `STATUS` |
| `auth-provider` (`auth`) `<name>` | `src/auth/providers/<name>.py` (deny-by-default) + test | `create_app(auth_provider=...)` |
| `audit-backend` (`audit`) `<name>` | `src/audit/backends/<name>.py` + test | `create_app(audit_backend=...)`, the package's `__all__` |
| `health-check` (`hc`) `<name>` | `src/checks/<name>.py` + test | `create_app(health_checks=[...])` |
| `middleware` (`mw`) `<name>` | pure-ASGI `src/middleware/<name>.py` + test | `stack.py`, innermost |
| `route` (`r`) `<name>` | operational `GET /<name>` in `src/routes/` + test | `create_app()` in `src/app.py` |
| `metric` (`m`) `<name> [--type histogram] [--labels a,b] [--module m]` | a counter / histogram in `src/metrics/<module>.py` | `/metrics` |

Common options: `--service` (which service's `main.py` / `DOMAINS`), `--no-wire` (create the
files only), `--tests/--no-tests`, `--dry-run`. `domain new`, `crud` and `service new` remain
as long forms.

**Endpoints** are stubs that work from the start: an item endpoint (`/v1/orders/{order_id}/cancel`)
loads the entity, a collection one (`/v1/orders/search`, `--collection`) the list, and
POST/PUT/PATCH/DELETE record an audit event. Collection routes are inserted before the `/{id}`
routes so those do not capture them. Domains made with `--no-crud` start with an empty router
for exactly this.

## The CRUD wizard

`blitz crud` (or `make crud`) asks the entity name, domain, service (when there are several) and
fields (name, type, required), then generates the domain. With arguments it asks only for what
is missing: `blitz crud Product -f title:str -f price:float -f notes:str?` asks nothing.

Field types: `str`, `int`, `float`, `bool`, `date`, `datetime`, `uuid`; `?` marks a field
optional. Each field appears in the persisted model, the create request (required unless `?`;
`str` is 1–255 characters) and the update request (always optional), and the generated tests
exercise them all. Add validators, defaults, enums or relations to the generated code.

**Non-interactive.** Questions are asked only on a terminal outside CI (`CI` unset).
Otherwise, or with `--no-interactive`, every question takes its default and one without a
default (the entity name) is an error naming the argument to pass. `domain remove` needs
`--yes` there. `--interactive` forces prompts.

## Integrations: `blitz add`

`blitz add` lists them; `blitz add <name> [--domain D ...]` wires one in a single step:

| Integration | Adds |
| --- | --- |
| `redis` | `RedisStore` (`src/store/redis.py`), `REDIS_URL`, `check_redis`, a compose `redis`, `redis` dependency |
| `postgres` | `PostgresStore` on a JSONB table, `DATABASE_URL` (secret), `check_postgres`, a compose `postgres`, `asyncpg` (+ mypy ignore) |

Settings go into `Settings` and `.env.example`, the check into the service's `health_checks`,
and the dependency is installed with `uv add` (`--skip-install` prints the command instead).
`--domain orders` switches that domain's `bootstrap()` from `InMemoryStore` to the
integration's store and registers the connection's close on the domain's `closers`. The store
is used only while the setting is set, so tests and local runs without the service keep the
in-memory store. Run it again with `--domain` to switch more domains.

## Project tools

| Command | Does |
| --- | --- |
| `blitz info` | CLI and Python versions, locked framework versions, services, domains, config |
| `blitz doctor [--import] [--strict]` | Checks the project's rules: the domain contract, registration, test tiers, Dockerfiles that run another service, `Settings` fields missing from `.env.example`. `--import` also imports every service's domains in the project venv and runs `create_app()`'s contract check. Exits 1 on errors (`--strict`: warnings too) |
| `blitz domain list` / `remove <name> [--yes]` | Domains, the services serving them, tests; delete + unregister |
| `blitz service list` | Services and their domains |
| `blitz template list` / `show <set>` | Template sets, placeholders, output files and where each comes from |

## Configuration: `[tool.blitz]`

```toml
# pyproject.toml
[tool.blitz]
templates = "templates"      # the project's own templates (see below)
default-service = "api"      # service generators register with / wire into
tests = true                 # generate tests; --tests / --no-tests override it
```

## Templates

`blitz_cli/templates/<set>/` mirrors the project layout. Every `*.tmpl` file is rendered with
Python's `string.Template`: `$name` / `${Entity}` placeholders in both the path and the content,
`$$` for a literal `$`, and the `.tmpl` suffix dropped. `template.toml` holds the set's
`description`, and may `extends = "<set>"` another set and `exclude` some of its files
(`domain-bare`, used by `--no-crud`, extends `domain` this way). Integrations are sets named
`integration-<name>` whose `template.toml` also declares settings, compose service, health
check, dependencies and the domain wiring snippet (see `blitz_cli/commands/integrations.py`).

**Project templates.** With `[tool.blitz] templates = "templates"`, `templates/<set>/` in the
project overrides the built-in set file by file: `templates/domain/src/domains/$name/models.py.tmpl`
replaces only the model. New directories add sets (an `integration-<name>` adds an integration).
`blitz template show <set>` marks the files that come from the project.

| Set | Placeholders |
| --- | --- |
| `domain`, `domain-bare` | `name`, `route`, `Plural`, `Entity`, `entity`, `entity_words`, `service`; field snippets from `blitz_cli/fields.py` (`model_fields`, `create_fields`, `update_fields`, `sample`, `fuzz_strategy`, …) |
| `service` | `service` |
| `auth-provider`, `audit-backend`, `health-check`, `middleware`, `route` | `slug`, `Pascal`, `words`, `route` |

A test checks that the CLI supplies a value for every placeholder of the built-in sets.

## Development

```bash
cd cli && make verify      # format check, lint, mypy --strict, tests (also run by the root `make verify`)
```
