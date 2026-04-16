Scaffold a new domain using the four-layer monorepo pattern and wire it into the API service.

Arguments: $ARGUMENTS

The argument is the domain name (e.g. `orders`, `users`, `billing`).  Use it as-is for the
package name (lowercase, underscores).  Derive a PascalCase prefix for class names (e.g.
`orders` → `Orders`, `user_profile` → `UserProfile`).

See `src/domains/example/` for the canonical reference implementation.

## What to create

### 1. Package skeleton

```
src/domains/<name>/
├── __init__.py       # empty
├── models.py         # Pydantic entity + request models
├── repository.py     # Data-access layer (depends on KeyValueStore protocol)
├── service.py        # Business logic (depends on Repository)
├── dependencies.py   # FastAPI Annotated dependency aliases
└── domain.py         # Domain container + router + make_router() + bootstrap()
```

### 2. `src/domains/<name>/models.py`

```python
from __future__ import annotations

from pydantic import BaseModel


class <Name>Item(BaseModel):
    id: str
    name: str
    # add domain-specific fields here


class Create<Name>ItemRequest(BaseModel):
    name: str


class Update<Name>ItemRequest(BaseModel):
    name: str | None = None
```

### 3. `src/domains/<name>/repository.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from .models import <Name>Item

if TYPE_CHECKING:
    from store.protocol import KeyValueStore


class <Name>Repository:
    def __init__(self, store: KeyValueStore[str, <Name>Item]) -> None:
        self._store = store

    async def find_by_id(self, item_id: str) -> <Name>Item | None:
        return await self._store.get(item_id)

    async def save(self, item: <Name>Item) -> <Name>Item:
        await self._store.set(item.id, item)
        return item

    async def delete(self, item_id: str) -> bool:
        return await self._store.delete(item_id)

    async def find_all(self) -> list[<Name>Item]:
        keys = await self._store.keys()
        items = [await self._store.get(k) for k in keys]
        return [i for i in items if i is not None]
```

### 4. `src/domains/<name>/service.py`

```python
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from service import Service

from .models import <Name>Item, Create<Name>ItemRequest, Update<Name>ItemRequest
from .repository import <Name>Repository

if TYPE_CHECKING:
    from context import RequestContext


class <Name>Service(Service):
    def __init__(self, repository: <Name>Repository) -> None:
        self._repo = repository

    async def get(self, item_id: str, ctx: RequestContext) -> <Name>Item | None:
        return await self._repo.find_by_id(item_id)

    async def list_all(self, ctx: RequestContext) -> list[<Name>Item]:
        return await self._repo.find_all()

    async def create(self, request: Create<Name>ItemRequest, ctx: RequestContext) -> <Name>Item:
        item = <Name>Item(id=str(uuid.uuid4()), name=request.name)
        ctx.set("last_created_item_id", item.id)
        return await self._repo.save(item)
```

### 5. `src/domains/<name>/dependencies.py`

```python
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from context import RequestContext

from .service import <Name>Service


def _get_<name>_service(request: Request) -> <Name>Service:
    domain = request.app.state.domains["domains.<name>.domain"]
    return domain.service


def _get_ctx(request: Request) -> RequestContext:
    return request.state.ctx


<Name>ServiceDep = Annotated[<Name>Service, Depends(_get_<name>_service)]
RequestContextDep = Annotated[RequestContext, Depends(_get_ctx)]
```

### 6. `src/domains/<name>/domain.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from store.memory import InMemoryStore

from .dependencies import <Name>ServiceDep, RequestContextDep
from .models import <Name>Item, Create<Name>ItemRequest
from .repository import <Name>Repository
from .service import <Name>Service

if TYPE_CHECKING:
    from config import Settings


class <Name>Domain:
    def __init__(self, service: <Name>Service) -> None:
        self.service = service


_router = APIRouter(prefix="/<name>", tags=["<name>"])


@_router.get("/", response_model=list[<Name>Item])
async def list_items(service: <Name>ServiceDep, ctx: RequestContextDep) -> list[<Name>Item]:
    return await service.list_all(ctx)


@_router.post("/", response_model=<Name>Item, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: Create<Name>ItemRequest, service: <Name>ServiceDep, ctx: RequestContextDep
) -> <Name>Item:
    return await service.create(body, ctx)


@_router.get("/{item_id}", response_model=<Name>Item)
async def get_item(item_id: str, service: <Name>ServiceDep, ctx: RequestContextDep) -> <Name>Item:
    item = await service.get(item_id, ctx)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


def make_router() -> APIRouter:
    return _router


async def bootstrap(settings: Settings, **kwargs) -> <Name>Domain:
    store: InMemoryStore[str, <Name>Item] = InMemoryStore()
    repository = <Name>Repository(store=store)
    service = <Name>Service(repository=repository)
    return <Name>Domain(service=service)
```

**Rules:**
- `InMemoryStore` must only appear in `bootstrap()`, never in repo/service constructors
- Domain key: always `"domains.<package>.<module>"` — e.g. `domains.orders.domain`
- `make_router()` returns the module-level `_router`; never creates a new router per call
- Every service method accepts `ctx: RequestContext` as its last parameter

### 7. Wire into `src/services/api/main.py`

Import the domain module and add it to `create_app()`:

```python
from domains.<name> import domain as <name>_domain

app = create_app(settings=settings, domains=[example_domain, <name>_domain])
```

Append to the existing `domains=[...]` list rather than replacing it.

### 8. Tests

Create the full three-layer test suite:

```
tests/domains/<name>/
├── __init__.py
├── unit/
│   ├── __init__.py
│   └── test_service.py      # unit-test service methods with AsyncMock
├── integration/
│   ├── __init__.py
│   └── test_routes.py       # HTTP route tests via asgi-lifespan client
└── fuzz/
    ├── __init__.py
    └── test_fuzz.py          # Hypothesis @given property tests
```

Integration tests must use the `client` fixture from `tests/conftest.py` (or
construct one with `asgi_lifespan.LifespanManager`) so `bootstrap()` runs before
any request and `app.state.domains` is populated.

## After scaffolding

1. Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
2. Run `uv run pytest -v` — all existing tests must still pass plus the new ones
3. Confirm the new route appears in the OpenAPI schema: `make dev` then `/docs`

## Conventions

- `from __future__ import annotations` on every new file
- Line length: 100 characters
- Ruff only — no bare `except:`, always name the exception type
- All domain imports inside the package must be relative (`from .models import ...`)
