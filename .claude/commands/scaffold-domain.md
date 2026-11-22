Scaffold a new domain using the four-layer pattern and wire it into the API service.

Arguments: $ARGUMENTS

The first argument is the domain name (snake_case, e.g. `orders`, `user_profiles`). An optional
second argument is the PascalCase entity name; by default it is the singular of the domain name
(`orders` → `Order`, `categories` → `Category`).

## 1. Generate

Run the generator — do not hand-write the files:

```bash
make domain DOMAIN=<name> [ENTITY=<Entity>] [SERVICE=api]
# same as: uv run --project cli blitz domain new <name> [--entity <Entity>] [--service api]
# with real fields (types: str int float bool date datetime uuid; `?` = optional):
uv run --project cli blitz domain new <name> --entity <Entity> -f title:str -f price:float -f notes:str?
```

It creates:

```
src/domains/<name>/
├── models.py        # <Entity>, Create<Entity>Request, Update<Entity>Request
├── errors.py        # <Entity>ErrorCode + <Entity>Error(DomainError) with code → HTTP status
├── repository.py    # <Entity>Repository(store: KeyValueStore[str, <Entity>])
├── service.py       # <Entity>Service — Result[T, <Entity>Error], audit on writes
├── dependencies.py  # <Entity>ServiceDep
└── domain.py        # <Plural>Domain (+ aclose), ResultRouter CRUD routes, make_router(), bootstrap()

tests/domains/<name>/{unit,integration,fuzz}/   # passing test skeletons
```

and appends the module to `src/services/<service>/domains.py`. If the script refuses (name
taken, invalid name, unknown service), report that to the user instead of working around it.
`--dry-run` lists the files without writing them.

## 2. Customise

Adapt the generated code to what the user described:

- **Models** — pass the real fields with `-f` when generating; add validators and defaults here.
- **Errors** — add codes (e.g. `CONFLICT`) and map each to a status in `STATUS`. 5xx codes
  never expose their `message` to clients.
- **Service** — add business rules. Keep every method returning `Result[T, <Entity>Error]` and
  taking `ctx: RequestContext` last. Catch storage exceptions only at the repository call and
  route them through `_storage_failure`.
- **Routes** — keep handlers as thin delegates. `response_model` is inferred from
  `Result[T, ...]`; shared deps (`RequestContextDep`, `SettingsDep`, …) come from `deps`.
- **Bootstrap** — swap `InMemoryStore` for a real store here only; close it in `aclose()`.
  Settings and extra resources are on `boot.settings` / `boot.extra`.
- **Tests** — extend all three tiers to cover the new fields, rules and error codes.

The rules the result must follow are in `AGENTS.md` (domain table, contract, gotchas).
`src/domains/example/` is the fuller reference (OpenTelemetry spans, audit metadata).

## 3. Verify

1. `make verify` — format, lint, mypy and every test (old and new) must pass
2. The routes appear under `/v1/<name-with-dashes>` in `/docs` (`make dev`)
