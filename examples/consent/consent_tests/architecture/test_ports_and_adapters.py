"""Every port is an abstract base class with a production adapter and a test fake."""

import dataclasses
import importlib
import inspect
import pkgutil
from abc import ABC
from types import ModuleType

import pytest

import consent_app
import consent_tests.fakes

_SKIP = (
    "consent_app.main",
    "consent_app.adapters.sql.migrate",
    "consent_app.adapters.api_keys",
    "consent_app.adapters.seed",
)


def _load(package: ModuleType) -> list[ModuleType]:
    names = [i.name for i in pkgutil.walk_packages(package.__path__, f"{package.__name__}.")]
    return [package, *(importlib.import_module(n) for n in names if not n.startswith(_SKIP))]


_load(consent_app)
_load(consent_tests.fakes)

from consent_app import ports  # noqa: E402 — after every implementation is imported

PORTS = [
    obj
    for _, obj in inspect.getmembers(ports, inspect.isclass)
    # Exceptions and dataclasses (values a port returns) are part of a contract, not ports.
    if obj.__module__.startswith("consent_app.ports")
    and not issubclass(obj, Exception)
    and not dataclasses.is_dataclass(obj)
]


def _implementations(port: type) -> list[type]:
    seen: list[type] = []
    stack: list[type] = list(port.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in seen:
            seen.append(cls)
            stack.extend(cls.__subclasses__())
    return [c for c in seen if not inspect.isabstract(c)]


def test_ports_were_discovered() -> None:
    assert {p.__name__ for p in PORTS} >= {
        "ConsentLedger",
        "ConsentUnitOfWork",
        "PurposeRepository",
    }


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_every_port_is_abstract(port: type) -> None:
    assert issubclass(port, ABC)
    assert inspect.isabstract(port)


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_every_port_has_an_adapter_and_a_fake(port: type) -> None:
    impls = _implementations(port)
    assert any(c.__module__.startswith("consent_app.") for c in impls), "no adapter"
    assert any(c.__module__.startswith("consent_tests.fakes") for c in impls), "no fake"
