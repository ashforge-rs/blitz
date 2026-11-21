"""ResultRouter: Result unwrapping, response_model inference, DomainError → problem."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from returns.result import Failure, Result, Success

from errors.domain import DomainError
from errors.handlers import register_error_handlers
from routing import ResultRouter


class Code(StrEnum):
    MISSING = "missing"
    BROKEN = "broken"
    UNMAPPED = "unmapped"


@dataclass(frozen=True, slots=True)
class ThingError(DomainError[Code]):
    STATUS: ClassVar[Mapping[str, int]] = {Code.MISSING: 404, Code.BROKEN: 503}


class Thing(BaseModel):
    name: str


router = ResultRouter(prefix="/things")


@router.get("/ok")
async def ok() -> Result[Thing, ThingError]:
    return Success(Thing(name="a"))


@router.get("/missing")
async def missing() -> Result[Thing, ThingError]:
    return Failure(ThingError(Code.MISSING, "thing 'x' not found"))


@router.get("/broken")
async def broken() -> Result[Thing, ThingError]:
    return Failure(ThingError(Code.BROKEN, "db password=hunter2 rejected"))


@router.get("/unmapped")
async def unmapped() -> Result[Thing, ThingError]:
    return Failure(ThingError(Code.UNMAPPED, "no status declared"))


@router.get("/exc")
async def exc() -> Result[Thing, Exception]:
    return Failure(KeyError("raw"))


@router.get("/sync")
def sync() -> Result[Thing, ThingError]:
    return Success(Thing(name="sync"))


@router.get("/plain")
async def plain() -> Thing:
    return Thing(name="plain")


@router.delete("/gone", status_code=204)
async def gone() -> Result[None, ThingError]:
    return Success(None)


@router.get("/untyped", response_model=None)
async def untyped() -> Result[Thing, ThingError]:
    return Success(Thing(name="u"))


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app, is_production=True)
    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


async def test_success_is_unwrapped(client):
    r = await client.get("/things/ok")
    assert r.status_code == 200
    assert r.json() == {"name": "a"}


async def test_sync_endpoint_is_unwrapped(client):
    assert (await client.get("/things/sync")).json() == {"name": "sync"}


async def test_plain_return_passes_through(client):
    assert (await client.get("/things/plain")).json() == {"name": "plain"}


async def test_success_none_with_204(client):
    r = await client.delete("/things/gone")
    assert r.status_code == 204
    assert r.content == b""


async def test_domain_error_becomes_problem(client):
    r = await client.get("/things/missing")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["detail"] == "thing 'x' not found"
    assert body["code"] == "missing"


async def test_5xx_domain_error_hides_message(client):
    r = await client.get("/things/broken")
    assert r.status_code == 503
    assert r.json()["detail"] == "Service Unavailable"
    assert "hunter2" not in r.text


async def test_unmapped_code_is_500(client):
    r = await client.get("/things/unmapped")
    assert r.status_code == 500
    assert r.json()["code"] == "unmapped"


async def test_failure_holding_exception_is_reraised(client):
    r = await client.get("/things/exc")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal server error"


def test_response_model_is_inferred_from_result(app):
    schema = app.openapi()
    ok_response = schema["paths"]["/things/ok"]["get"]["responses"]["200"]
    assert ok_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Thing"
    }


def test_explicit_response_model_none_is_respected(app):
    response = app.openapi()["paths"]["/things/untyped"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {}
