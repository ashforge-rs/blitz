"""Ports are abstract base classes; every port has a real adapter and a test fake.

Discovered, not listed: a new port without an implementation, or an
implementation that doesn't inherit its port, fails here.
"""

import importlib
import inspect
import pkgutil
from abc import ABC
from types import ModuleType

import pytest

import todo_app
import todo_tests.fakes
from todo_app.auth.token_verifier import TokenVerifier
from todo_app.kernel import AuditTrail, Clock, IdempotencyStore, IdGenerator

#: Ports that live outside a context's ``ports/`` package.
SHARED_PORTS: list[type] = [Clock, IdGenerator, AuditTrail, IdempotencyStore, TokenVerifier]

#: Entry points run on import; everything else is safe to load.
_SKIP = ("todo_app.main", "todo_app.__main__", "todo_app.cli.__main__")


def _load(package: ModuleType) -> list[ModuleType]:
    names = [i.name for i in pkgutil.walk_packages(package.__path__, f"{package.__name__}.")]
    return [package, *(importlib.import_module(n) for n in names if not n.startswith(_SKIP))]


APP_MODULES = _load(todo_app)
FAKE_MODULES = _load(todo_tests.fakes)


def _context_ports() -> list[type]:
    found = []
    for module in APP_MODULES:
        if ".ports." not in module.__name__:
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and not issubclass(obj, Exception):
                found.append(obj)
    return found


PORTS = SHARED_PORTS + _context_ports()
#: Ports a use case depends on, so unit tests need a fake.  TokenVerifier is consumed
#: only by the HTTP auth provider and is exercised end to end through HTTP.
FAKED_PORTS = [p for p in PORTS if p is not TokenVerifier]


def _implementations(port: type) -> list[type]:
    seen: list[type] = []
    stack: list[type] = list(port.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in seen:
            seen.append(cls)
            stack.extend(cls.__subclasses__())
    return [c for c in seen if not inspect.isabstract(c)]


def _name(port: type) -> str:
    return f"{port.__module__.removeprefix('todo_app.')}.{port.__qualname__}"


def test_ports_were_discovered() -> None:
    names = {p.__name__ for p in PORTS}
    assert {"UserRepository", "UsersUnitOfWork", "TodoRepository", "TodoTelemetry"} <= names


@pytest.mark.parametrize("port", PORTS, ids=_name)
def test_every_port_is_an_abstract_base_class(port: type) -> None:
    assert issubclass(port, ABC), f"{_name(port)} must subclass abc.ABC"
    assert inspect.isabstract(port), f"{_name(port)} declares no @abstractmethod"
    with pytest.raises(TypeError, match="abstract"):
        port()


@pytest.mark.parametrize("port", PORTS, ids=_name)
def test_every_port_has_a_production_adapter_that_inherits_it(port: type) -> None:
    adapters = [c for c in _implementations(port) if c.__module__.startswith("todo_app.")]
    assert adapters, f"{_name(port)} has no concrete subclass in todo_app"


@pytest.mark.parametrize("port", FAKED_PORTS, ids=_name)
def test_every_use_case_port_has_a_test_fake_that_inherits_it(port: type) -> None:
    fakes = [c for c in _implementations(port) if c.__module__.startswith("todo_tests.fakes")]
    assert fakes, f"{_name(port)} has no fake in todo_tests/fakes"


def test_an_incomplete_adapter_cannot_be_instantiated() -> None:
    class Incomplete(Clock):
        pass

    with pytest.raises(TypeError, match="abstract method"):
        Incomplete()  # type: ignore[abstract]  # the point of the test
