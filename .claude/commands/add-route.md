Add an operational (non-domain) route for the feature described below.

Arguments: $ARGUMENTS

## Start with the generator

Do not create the files by hand:

```bash
uv run --project cli blitz g r <name> --dry-run   # see what changes
uv run --project cli blitz g r <name>
```

It creates `src/routes/<name>.py` (`GET /<name>` with a response model) and
`tests/global/integration/test_route_<name>.py`, and adds `app.include_router(<name>.router)`
to `create_app()` in `src/app.py`. Use it only after deciding the route belongs outside a domain
(next section); for domain endpoints use `uv run --project cli blitz g endpoint <domain> <name>`.

## First, decide where it belongs

- **Business feature** (a resource with data, rules, CRUD — orders, invoices, profiles): this is a
  domain, not a route. Use `/scaffold-domain <name>`, or add the endpoint to an existing domain's
  `domain.py` on its `ResultRouter`, backed by a service method. Stop here.
- **Operational endpoint** (probes, diagnostics, version info, admin tooling, unprefixed by
  `API_PREFIX` like `/live` and `/metrics`): continue below.

Follow the rules in `AGENTS.md`, especially Gotchas #2: names used in route signatures must be real
imports, not `TYPE_CHECKING` imports.

## Instructions

1. Shape the generated `src/routes/<name>.py` (module-level `router = APIRouter(...)`):
   - Typed Pydantic response models defined at the top of the file
   - `RequestContextDep` / `SettingsDep` from `deps` instead of reaching into `request.state`
   - `Depends(get_auth_context)` from `auth.dependency` on anything that needs auth
   - Raise `AppError` subclasses (`errors.exceptions`) or `HTTPException` for errors; every error
     body is RFC 9457 problem JSON automatically

2. The generator registers it in `create_app()` (`src/app.py`) next to the built-in routes:
   `app.include_router(<name>.router)`. Operational routes are
   never prefixed with `API_PREFIX`.

3. Extend the generated test `tests/global/integration/test_route_<name>.py` (`client` fixture, or
   `make_app(...)` + `make_client(app)` when the test needs different settings).

4. Run `make verify`; it must exit 0.
