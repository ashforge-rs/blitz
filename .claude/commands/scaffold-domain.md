Scaffold a new service-oriented domain and wire it into the application.

Arguments: $ARGUMENTS

The argument is the domain name (e.g. `orders`, `users`, `billing`).  Use it as-is for the
package name (lowercase, underscores).  Derive a PascalCase prefix for class names (e.g.
`orders` → `Orders`, `user_profile` → `UserProfile`).

## What to create

### 1. Package skeleton

```
src/<name>/
├── __init__.py      # empty
└── domain.py        # service + domain + router + bootstrap
```

### 2. `src/<name>/domain.py`

Follow this exact structure — four clearly separated sections:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

from service import Service

if TYPE_CHECKING:
    from config import Settings

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class <Name>Service(Service):
    """Business logic for the <name> bounded context."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # Add domain methods here, e.g.:
    # async def find_by_id(self, id: str) -> dict | None: ...
    # async def create(self, payload: dict) -> dict: ...


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class <Name>Domain:
    """
    Holds bootstrapped service instances for the *<name>* bounded context.

    Access from a route handler::

        domain: <Name>Domain = request.app.state.domains["<name>.domain"]
    """

    def __init__(self, service: <Name>Service) -> None:
        self.service = service


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_router = APIRouter(prefix="/<name>", tags=["<name>"])


@_router.get("/")
async def list_<name>(request: Request) -> list[Any]:
    domain: <Name>Domain = request.app.state.domains["<name>.domain"]
    return []


def make_router() -> APIRouter:
    """Return the router to be included by create_app()."""
    return _router


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


async def bootstrap(settings: Settings, **kwargs: Any) -> <Name>Domain:
    """
    Called once at application startup (lifespan).

    Initialise external clients, DB pools, etc. here.
    Return the fully-constructed domain instance; it will be stored on
    ``app.state.domains["<name>.domain"]``.
    """
    service = <Name>Service(settings=settings)
    return <Name>Domain(service=service)
```

**Rules for `domain.py`:**
- `<Name>Service(Service)` — inherits from `service.Service`; declare all dependencies
  (DB pools, HTTP clients, config) in `__init__`; no logic in the constructor
- `<Name>Domain` — a thin holder; one service per bounded context is the default; add more
  if the domain genuinely has multiple orthogonal concerns
- `make_router()` — always returns the module-level `_router`; called at `create_app()` time
  so OpenAPI schema is always complete at startup
- `bootstrap(settings, **kwargs)` — async; called once during lifespan; must be idempotent;
  raise on unrecoverable errors (the lifespan will propagate and abort startup)
- Domain key: always `"<package>.<module>"` — e.g. `orders.domain` for
  `src/orders/domain.py`

### 3. Wire into `src/main.py`

Import the domain module and pass it to `create_app()`:

```python
from <name> import domain as <name>_domain

app = create_app(
    domains=[<name>_domain],   # add alongside any existing domains
)
```

If `main.py` already has a `domains=[...]` list, append to it rather than replacing it.

### 4. Add Pydantic response models (optional but recommended)

If the domain exposes resources, define response/request models at the top of `domain.py`
(or in a sibling `schemas.py`) using `pydantic.BaseModel`.  Return them from route handlers
for automatic OpenAPI docs and serialisation.

```python
from pydantic import BaseModel

class <Name>Item(BaseModel):
    id: str
    name: str
```

### 5. Tests

Create `tests/test_<name>.py`:

```python
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from <name> import domain as <name>_domain


@pytest.fixture
async def client():
    app = create_app(domains=[<name>_domain])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_<name>_empty(client):
    response = await client.get("/<name>/")
    assert response.status_code == 200
    assert response.json() == []
```

Add more tests covering the service methods once they are implemented.

## After scaffolding

1. Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
2. Run `uv run pytest -v` — all existing tests must still pass plus the new ones
3. Confirm the new route appears in the OpenAPI schema by checking `GET /openapi.json`
   (start the dev server with `make dev` and visit `/docs`)

## Conventions

- `from __future__ import annotations` on every new file
- Line length: 100 characters
- No `mypy` — Ruff only
- No bare `except:` — always name the exception type
- Avoid importing the domain class at module level in `main.py` to keep startup order explicit
