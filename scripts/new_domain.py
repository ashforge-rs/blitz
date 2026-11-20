"""
Scaffold a new domain package plus its tests, and register it with a service.

Usage::

    uv run python scripts/new_domain.py orders            # entity: Order
    uv run python scripts/new_domain.py people --entity Person
    uv run python scripts/new_domain.py billing --service worker --no-register

or ``make domain DOMAIN=orders [ENTITY=Order] [SERVICE=api]``.

Generates ``src/domains/<name>/`` (models, errors, repository, service,
dependencies, domain) following the reference domain in ``src/domains/example``,
a unit / integration / fuzz test skeleton under ``tests/domains/<name>/``, and
appends the module to ``src/services/<service>/domains.py``.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RESERVED = {"example"}


def pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def snake(pascal_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", pascal_name).lower()


def default_entity(name: str) -> str:
    """``orders`` → ``Order``, ``user_profiles`` → ``UserProfile``, ``billing`` → ``Billing``."""
    base = pascal(name)
    if base.endswith("ies") and len(base) > 3:
        return base[:-3] + "y"
    if base.endswith("s") and not base.endswith("ss") and len(base) > 1:
        return base[:-1]
    return base


# ── Templates ($-placeholders; see `render`) ─────────────────────────────────

FILES: dict[str, str] = {}

FILES["src/domains/$name/__init__.py"] = ""

FILES["src/domains/$name/models.py"] = '''\
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class $Entity(BaseModel):
    """Persisted $entity_words."""

    id: str
    name: str
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Create${Entity}Request(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class Update${Entity}Request(BaseModel):
    """All fields optional — only the ones sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
'''

FILES["src/domains/$name/errors.py"] = """\
from collections.abc import Mapping  # noqa: TC003 — evaluated at runtime by dataclass ClassVar
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from errors.domain import DomainError


class ${Entity}ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class ${Entity}Error(DomainError[${Entity}ErrorCode]):
    ${entity}_id: str | None = None

    STATUS: ClassVar[Mapping[str, int]] = {
        ${Entity}ErrorCode.NOT_FOUND: 404,
        ${Entity}ErrorCode.STORAGE_ERROR: 500,
    }
"""

FILES["src/domains/$name/repository.py"] = '''\
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.protocol import KeyValueStore

    from .models import $Entity


class ${Entity}Repository:
    """Data access for ${entity_words} records — depends only on the KeyValueStore protocol."""

    def __init__(self, store: KeyValueStore[str, $Entity]) -> None:
        self._store = store

    async def find_by_id(self, ${entity}_id: str) -> $Entity | None:
        return await self._store.get(${entity}_id)

    async def find_all(self) -> list[$Entity]:
        keys = await self._store.keys()
        found = [await self._store.get(k) for k in keys]
        return [x for x in found if x is not None]

    async def save(self, $entity: $Entity) -> $Entity:
        await self._store.set($entity.id, $entity)
        return $entity

    async def delete(self, ${entity}_id: str) -> bool:
        return await self._store.delete(${entity}_id)
'''

FILES["src/domains/$name/service.py"] = '''\
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from loguru import logger
from returns.result import Failure, Result, Success

from audit.backend import AuditBackend, AuditIntegrity, AuditResult
from audit.helpers import log_operation
from service import Service

from .errors import ${Entity}Error, ${Entity}ErrorCode
from .models import $Entity, Create${Entity}Request, Update${Entity}Request

if TYPE_CHECKING:
    from context import RequestContext

    from .repository import ${Entity}Repository


class ${Entity}Service(Service):
    """Business logic for $name. Every method returns ``Result[T, ${Entity}Error]``."""

    def __init__(
        self,
        repository: ${Entity}Repository,
        audit_backend: AuditBackend,
        audit_integrity: AuditIntegrity,
    ) -> None:
        self._repo = repository
        self._audit = audit_backend
        self._integrity = audit_integrity

    def _principal(self, ctx: RequestContext) -> str | None:
        return cast("str | None", ctx.get("principal"))

    async def _audit_op(
        self,
        ctx: RequestContext,
        operation: str,
        ${entity}_id: str | None,
        result: AuditResult = AuditResult.SUCCESS,
    ) -> None:
        await log_operation(
            self._audit, self._integrity, ctx, operation, result=result, resource_id=${entity}_id
        )

    async def _storage_failure(
        self, exc: Exception, ctx: RequestContext, operation: str, ${entity}_id: str | None = None
    ) -> Failure[${Entity}Error]:
        logger.error(f"{operation}.error", ${entity}_id=${entity}_id, error=str(exc))
        if operation.split(".")[-1] in {"create", "update", "delete"}:
            await self._audit_op(ctx, operation, ${entity}_id, AuditResult.FAILURE)
        return Failure(${Entity}Error(${Entity}ErrorCode.STORAGE_ERROR, str(exc), ${entity}_id))

    @staticmethod
    def _not_found(${entity}_id: str) -> Failure[${Entity}Error]:
        message = f"{${entity}_id!r} not found"
        return Failure(${Entity}Error(${Entity}ErrorCode.NOT_FOUND, message, ${entity}_id))

    async def get(self, ${entity}_id: str, ctx: RequestContext) -> Result[$Entity, ${Entity}Error]:
        try:
            found = await self._repo.find_by_id(${entity}_id)
        except Exception as exc:  # noqa: BLE001 — storage boundary
            return await self._storage_failure(exc, ctx, "$name.get", ${entity}_id)
        return Success(found) if found is not None else self._not_found(${entity}_id)

    async def list_all(self, ctx: RequestContext) -> Result[list[$Entity], ${Entity}Error]:
        try:
            return Success(await self._repo.find_all())
        except Exception as exc:  # noqa: BLE001 — storage boundary
            return await self._storage_failure(exc, ctx, "$name.list_all")

    async def create(
        self, request: Create${Entity}Request, ctx: RequestContext
    ) -> Result[$Entity, ${Entity}Error]:
        $entity = $Entity(
            id=str(uuid.uuid4()),
            name=request.name,
            created_by=self._principal(ctx),
            updated_by=self._principal(ctx),
        )
        try:
            saved = await self._repo.save($entity)
        except Exception as exc:  # noqa: BLE001 — storage boundary
            return await self._storage_failure(exc, ctx, "$name.create")
        await self._audit_op(ctx, "$name.create", saved.id)
        return Success(saved)

    async def update(
        self, ${entity}_id: str, request: Update${Entity}Request, ctx: RequestContext
    ) -> Result[$Entity, ${Entity}Error]:
        try:
            found = await self._repo.find_by_id(${entity}_id)
            if found is None:
                return self._not_found(${entity}_id)
            changes = request.model_dump(exclude_none=True)
            changes |= {"updated_at": datetime.now(UTC), "updated_by": self._principal(ctx)}
            updated = found.model_copy(update=changes)
            saved = await self._repo.save(updated)
        except Exception as exc:  # noqa: BLE001 — storage boundary
            return await self._storage_failure(exc, ctx, "$name.update", ${entity}_id)
        await self._audit_op(ctx, "$name.update", ${entity}_id)
        return Success(saved)

    async def delete(self, ${entity}_id: str, ctx: RequestContext) -> Result[None, ${Entity}Error]:
        try:
            deleted = await self._repo.delete(${entity}_id)
        except Exception as exc:  # noqa: BLE001 — storage boundary
            return await self._storage_failure(exc, ctx, "$name.delete", ${entity}_id)
        if not deleted:
            return self._not_found(${entity}_id)
        await self._audit_op(ctx, "$name.delete", ${entity}_id)
        return Success(None)
'''

FILES["src/domains/$name/dependencies.py"] = """\
from typing import Annotated

from fastapi import Depends, Request

from state import get_domain

from .service import ${Entity}Service


def _get_${entity}_service(request: Request) -> ${Entity}Service:
    # Imported lazily: domain.py imports this module.
    from .domain import ${Plural}Domain

    return get_domain(request, ${Plural}Domain).service


${Entity}ServiceDep = Annotated[${Entity}Service, Depends(_get_${entity}_service)]
"""

FILES["src/domains/$name/domain.py"] = '''\
from typing import TYPE_CHECKING

from fastapi import APIRouter, status
from returns.result import Result

from deps import RequestContextDep
from routing import ResultRouter
from store.memory import InMemoryStore

from .dependencies import ${Entity}ServiceDep
from .errors import ${Entity}Error
from .models import $Entity, Create${Entity}Request, Update${Entity}Request
from .repository import ${Entity}Repository
from .service import ${Entity}Service

if TYPE_CHECKING:
    from bootstrap import BootstrapContext


class ${Plural}Domain:
    """What bootstrap() returns and get_domain() looks up."""

    def __init__(self, service: ${Entity}Service) -> None:
        self.service = service

    async def aclose(self) -> None:
        """Called on shutdown — close anything bootstrap() opened."""


_router = ResultRouter(prefix="/$route", tags=["$name"])


@_router.get("/")
async def list_$name(
    svc: ${Entity}ServiceDep, ctx: RequestContextDep
) -> Result[list[$Entity], ${Entity}Error]:
    return await svc.list_all(ctx)


@_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_$entity(
    body: Create${Entity}Request, svc: ${Entity}ServiceDep, ctx: RequestContextDep
) -> Result[$Entity, ${Entity}Error]:
    return await svc.create(body, ctx)


@_router.get("/{${entity}_id}")
async def get_$entity(
    ${entity}_id: str, svc: ${Entity}ServiceDep, ctx: RequestContextDep
) -> Result[$Entity, ${Entity}Error]:
    return await svc.get(${entity}_id, ctx)


@_router.patch("/{${entity}_id}")
async def update_$entity(
    ${entity}_id: str,
    body: Update${Entity}Request,
    svc: ${Entity}ServiceDep,
    ctx: RequestContextDep,
) -> Result[$Entity, ${Entity}Error]:
    return await svc.update(${entity}_id, body, ctx)


@_router.delete("/{${entity}_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_$entity(
    ${entity}_id: str, svc: ${Entity}ServiceDep, ctx: RequestContextDep
) -> Result[None, ${Entity}Error]:
    return await svc.delete(${entity}_id, ctx)


def make_router() -> APIRouter:
    return _router


async def bootstrap(boot: BootstrapContext) -> ${Plural}Domain:
    store: InMemoryStore[str, $Entity] = InMemoryStore()
    service = ${Entity}Service(
        repository=${Entity}Repository(store=store),
        audit_backend=boot.audit_backend,
        audit_integrity=boot.audit_integrity,
    )
    return ${Plural}Domain(service=service)
'''

for _sub in ("", "/unit", "/integration", "/fuzz"):
    FILES[f"tests/domains/$name{_sub}/__init__.py"] = ""

FILES["tests/domains/$name/unit/test_service.py"] = """\
from unittest.mock import MagicMock

import pytest
from returns.result import Failure, Success

from audit.backends.noop import NoopAuditBackend
from audit.integrity import NoIntegrity
from domains.$name.errors import ${Entity}ErrorCode
from domains.$name.models import $Entity, Create${Entity}Request, Update${Entity}Request
from domains.$name.repository import ${Entity}Repository
from domains.$name.service import ${Entity}Service
from store.memory import InMemoryStore


@pytest.fixture
def service() -> ${Entity}Service:
    store: InMemoryStore[str, $Entity] = InMemoryStore()
    return ${Entity}Service(
        repository=${Entity}Repository(store=store),
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )


@pytest.fixture
def ctx() -> MagicMock:
    mock = MagicMock()
    mock.request_id = "test-request-id"
    mock.get.return_value = None
    return mock


async def test_create_then_get(service, ctx):
    created = (await service.create(Create${Entity}Request(name="a"), ctx)).unwrap()
    assert await service.get(created.id, ctx) == Success(created)


async def test_get_missing_is_not_found(service, ctx):
    result = await service.get("missing", ctx)
    assert isinstance(result, Failure)
    assert result.failure().code == ${Entity}ErrorCode.NOT_FOUND


async def test_update_changes_only_sent_fields(service, ctx):
    created = (await service.create(Create${Entity}Request(name="a"), ctx)).unwrap()
    updated = (await service.update(created.id, Update${Entity}Request(name="b"), ctx)).unwrap()
    assert updated.name == "b"
    assert updated.created_at == created.created_at


async def test_delete_twice_is_not_found(service, ctx):
    created = (await service.create(Create${Entity}Request(name="a"), ctx)).unwrap()
    assert await service.delete(created.id, ctx) == Success(None)
    assert isinstance(await service.delete(created.id, ctx), Failure)
"""

FILES["tests/domains/$name/integration/test_routes.py"] = """\
from httpx import AsyncClient

BASE = "/v1/$route"


async def test_crud_roundtrip(client: AsyncClient) -> None:
    created = await client.post(f"{BASE}/", json={"name": "a"})
    assert created.status_code == 201
    ${entity}_id = created.json()["id"]

    assert (await client.get(f"{BASE}/{${entity}_id}")).json()["name"] == "a"
    assert (await client.patch(f"{BASE}/{${entity}_id}", json={"name": "b"})).json()["name"] == "b"
    assert (await client.delete(f"{BASE}/{${entity}_id}")).status_code == 204


async def test_missing_is_problem_404(client: AsyncClient) -> None:
    r = await client.get(f"{BASE}/missing")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "not_found"


async def test_invalid_body_is_422(client: AsyncClient) -> None:
    assert (await client.post(f"{BASE}/", json={"name": ""})).status_code == 422
"""

FILES["tests/domains/$name/fuzz/test_fuzz.py"] = """\
import asyncio
from unittest.mock import MagicMock

from hypothesis import given
from hypothesis import strategies as st

from audit.backends.noop import NoopAuditBackend
from audit.integrity import NoIntegrity
from domains.$name.models import $Entity, Create${Entity}Request
from domains.$name.repository import ${Entity}Repository
from domains.$name.service import ${Entity}Service
from store.memory import InMemoryStore

names = st.text(min_size=1, max_size=255).filter(str.strip)


def _service() -> ${Entity}Service:
    store: InMemoryStore[str, $Entity] = InMemoryStore()
    return ${Entity}Service(
        repository=${Entity}Repository(store=store),
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )


@given(name=names)
def test_create_then_get_roundtrip(name: str) -> None:
    async def run() -> None:
        svc, ctx = _service(), MagicMock()
        ctx.get.return_value = None
        created = (await svc.create(Create${Entity}Request(name=name), ctx)).unwrap()
        assert (await svc.get(created.id, ctx)).unwrap().name == name

    asyncio.run(run())
"""


def render(template: str, values: dict[str, str]) -> str:
    return Template(template).substitute(values)


def tidy(paths: list[Path]) -> None:
    """Sort imports and format the generated files (entity names change import order)."""
    py_files = [str(p) for p in paths if p.suffix == ".py"]
    for cmd in (["check", "--fix", "--select", "I", "--quiet"], ["format", "--quiet"]):
        try:
            subprocess.run(["ruff", *cmd, *py_files], check=True)  # noqa: S603, S607
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"warning: ruff {cmd[0]} failed ({exc}); run `make fmt`", file=sys.stderr)
            return


def register(root: Path, service: str, name: str) -> str | None:
    """Append the domain to ``src/services/<service>/domains.py``; return an error or None."""
    registry = root / "src" / "services" / service / "domains.py"
    if not registry.exists():
        return f"{registry.relative_to(root)} not found"
    text = registry.read_text()
    import_line = f"from domains.{name} import domain as {name}_domain\n"
    if import_line in text:
        return None
    imports = list(re.finditer(r"^from domains\.\w+ import domain as \w+\n", text, re.MULTILINE))
    closing = re.search(r"^DOMAINS:[^\n]*=\s*\[(?P<body>.*?)^\]", text, re.MULTILINE | re.DOTALL)
    if not imports or closing is None:
        return f"could not find the import block / DOMAINS list in {registry.relative_to(root)}"
    # Insert the list entry first (later offset), then the import.
    text = text[: closing.end() - 1] + f"    {name}_domain,\n" + text[closing.end() - 1 :]
    at = imports[-1].end()
    text = text[:at] + import_line + text[at:]
    registry.write_text(text)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("name", help="snake_case package name, e.g. orders")
    parser.add_argument("--entity", help="PascalCase entity class (default: singular of NAME)")
    parser.add_argument("--service", default="api", help="service to register with (default: api)")
    parser.add_argument("--no-register", action="store_true", help="do not edit the service")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    name: str = args.name
    if not NAME_RE.match(name) or name in RESERVED:
        parser.error(f"invalid domain name {name!r}: use snake_case, not {sorted(RESERVED)}")
    entity: str = args.entity or default_entity(name)
    if not ENTITY_RE.match(entity):
        parser.error(f"invalid entity {entity!r}: use PascalCase, e.g. Order")
    plural = pascal(name)
    root: Path = args.root

    if (root / "src" / "domains" / name).exists():
        print(f"error: src/domains/{name} already exists", file=sys.stderr)
        return 1

    values = {
        "name": name,
        "route": name.replace("_", "-"),
        "Plural": plural,
        "Entity": entity,
        "entity": snake(entity),
        "entity_words": snake(entity).replace("_", " "),
    }
    created: list[Path] = []
    for path_template, content in FILES.items():
        path = root / render(path_template, values)
        created.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(content, values))
        print(f"  created {path.relative_to(root)}")

    if not args.no_register:
        error = register(root, args.service, name)
        if error:
            print(f"warning: not registered — {error}", file=sys.stderr)
        else:
            created.append(root / "src" / "services" / args.service / "domains.py")
            print(f"  registered in src/services/{args.service}/domains.py")

    tidy(created)
    print(f"\nNext: `make check && make test`; routes are served at /v1/{values['route']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
