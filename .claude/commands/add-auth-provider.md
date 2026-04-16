Implement a concrete `AuthProvider` for the authentication scheme described below.

Arguments: $ARGUMENTS

## Instructions

Create `src/auth/providers/<slug>.py` containing a class that satisfies the `AuthProvider` protocol:

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
- Store the provider on the app via `create_app(auth_provider=MyAuthProvider())`
- If the scheme requires config (secret keys, JWKS URL, etc.) read values from `Settings` — add new fields to `src/config.py` if needed, and document them in `.env.example`
- Use `from __future__ import annotations` at the top

### After implementation
1. Show an example of protecting a route with `Depends(get_auth_context)` from `auth.dependency`
2. Write at least two tests: one for the 200 success path and one for the 401/403 rejection path
3. Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
