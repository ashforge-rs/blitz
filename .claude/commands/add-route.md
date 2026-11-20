Add an operational (non-domain) route for the feature described below.

Arguments: $ARGUMENTS

## First, decide where it belongs

- **Business feature** (a resource with data, rules, CRUD — orders, invoices, profiles): this is a
  domain, not a route. Use `/scaffold-domain <name>`, or add the endpoint to an existing domain's
  `domain.py` on its `ResultRouter`, backed by a service method. Stop here.
- **Operational endpoint** (probes, diagnostics, version info, admin tooling, unprefixed by
  `API_PREFIX` like `/live` and `/metrics`): continue below.

Follow the rules in `AGENTS.md`, especially Gotchas #2: names used in route signatures must be real
imports, not `TYPE_CHECKING` imports.

## Instructions

1. Create `src/routes/<name>.py` with a module-level `router = APIRouter(tags=["<name>"])`:
   - Typed Pydantic response models defined at the top of the file
   - `RequestContextDep` / `SettingsDep` from `deps` instead of reaching into `request.state`
   - `Depends(get_auth_context)` from `auth.dependency` on anything that needs auth
   - Raise `AppError` subclasses (`errors.exceptions`) or `HTTPException` for errors; every error
     body is RFC 9457 problem JSON automatically

2. Register it in `create_app()` (`src/app.py`) next to the built-in routes:
   `app.include_router(<name>.router)` in the "Built-in routes" block. Operational routes are
   never prefixed with `API_PREFIX`.

3. Add tests in `tests/global/integration/test_<name>.py` using the `client` fixture (or
   `make_app(...)` + `make_client(app)` when the test needs different settings).

4. Run `make verify`; it must exit 0.
