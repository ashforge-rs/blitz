Implement a concrete `AuthProvider` for the authentication scheme described below.

Arguments: $ARGUMENTS

## Start with the generator

Do not create the files by hand:

```bash
uv run --project cli blitz g auth <slug> --dry-run   # see what changes
uv run --project cli blitz g auth <slug>
```

It creates `src/auth/providers/<slug>.py` (a deny-by-default `<Slug>AuthProvider`) and
`tests/global/unit/test_auth_<slug>.py`, and passes `auth_provider=<Slug>AuthProvider()` to
`create_app()` in `src/services/api/main.py` (`--service <name>` for another service). If the
service already has an auth provider it says so and leaves `main.py` alone. Then implement
`authenticate()` / `authorize()` as described below.

## Instructions

The generated class in `src/auth/providers/<slug>.py` satisfies the `AuthProvider` protocol; fill in:

```python
from auth.protocol import AuthProvider  # for reference — do NOT inherit, it's a Protocol

class MyAuthProvider:
    async def authenticate(self, request: Request) -> <PrincipalType> | None:
        ...  # return None to reject with 401

    async def authorize(self, request: Request, principal: <PrincipalType>, context: RequestContext) -> bool:
        ...  # return False to reject with 403
```

### Rules
- `authenticate` must return `None` (never raise) when credentials are absent or invalid — the dependency converts that to a 401
- `authorize` receives the already-verified principal; use it to check scopes/roles
- The generator already passes it to `create_app(auth_provider=...)`; check the service's `main.py`
- If the scheme requires config (secret keys, JWKS URL, etc.) read values from `Settings` — add new fields to `src/config.py` if needed, and document them in `.env.example`
- No `from __future__ import annotations` — Python 3.14+ evaluates annotations lazily (PEP 649)

### After implementation
1. Show an example of protecting a route with `Depends(get_auth_context)` from `auth.dependency`
2. Write at least two tests: one for the 200 success path and one for the 401/403 rejection path
3. Run `make fmt && make verify` — `make verify` must exit 0
