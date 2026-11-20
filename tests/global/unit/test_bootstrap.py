"""Domain-module contract: validation at create_app() and lifespan bootstrap/teardown."""

import types

import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter

from app import create_app
from audit.backends.noop import NoopAuditBackend
from bootstrap import BootstrapContext, validate_domain_module


def _module(name: str, **hooks) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in hooks.items():
        setattr(module, key, value)
    return module


class _Closable:
    def __init__(self, log: list[str], name: str, *, fail: bool = False) -> None:
        self.log = log
        self.name = name
        self.fail = fail

    async def aclose(self) -> None:
        self.log.append(self.name)
        if self.fail:
            raise RuntimeError("boom")


def _closable_domain(name: str, log: list[str], *, fail: bool = False) -> types.ModuleType:
    # A distinct class per domain: get_domain() indexes instances by type.
    cls = type(f"{name}Domain", (_Closable,), {})

    async def bootstrap(boot: BootstrapContext) -> _Closable:
        return cls(log, name, fail=fail)

    return _module(name, bootstrap=bootstrap)


# ── validate_domain_module ───────────────────────────────────────────────────


def test_module_without_hooks_is_rejected():
    with pytest.raises(TypeError, match="exposes none of"):
        validate_domain_module(_module("typo", make_routers=lambda: APIRouter()))


def test_sync_bootstrap_is_rejected():
    def bootstrap(boot):
        return None

    with pytest.raises(TypeError, match="async"):
        validate_domain_module(_module("sync", bootstrap=bootstrap))


def test_legacy_bootstrap_signature_is_rejected():
    async def bootstrap(settings, audit_backend):
        return None

    with pytest.raises(TypeError, match="exactly one argument"):
        validate_domain_module(_module("legacy", bootstrap=bootstrap))


def test_non_callable_hook_is_rejected():
    with pytest.raises(TypeError, match="callable"):
        validate_domain_module(_module("bad", make_router="nope"))


def test_router_only_module_is_valid():
    validate_domain_module(_module("ok", make_router=lambda: APIRouter()))


def test_create_app_validates_domains(test_settings):
    with pytest.raises(TypeError, match="exposes none of"):
        create_app(settings=test_settings, domains=[_module("empty")])


# ── lifespan ─────────────────────────────────────────────────────────────────


async def test_bootstrap_receives_context_with_extra(test_settings):
    seen: list[BootstrapContext] = []

    async def bootstrap(boot: BootstrapContext) -> object:
        seen.append(boot)
        return object()

    backend = NoopAuditBackend()
    app = create_app(
        settings=test_settings,
        audit_backend=backend,
        domains=[_module("ctx", bootstrap=bootstrap)],
        extra_context={"db": "pool"},
    )
    async with LifespanManager(app):
        pass

    (boot,) = seen
    assert boot.settings is test_settings
    assert boot.audit_backend is backend
    assert boot.extra == {"db": "pool"}
    assert app.state.db == "pool"


async def test_domains_close_in_reverse_order(test_settings):
    log: list[str] = []
    app = create_app(
        settings=test_settings,
        domains=[_closable_domain("first", log), _closable_domain("second", log)],
    )
    async with LifespanManager(app):
        assert log == []
    assert log == ["second", "first"]


async def test_failing_aclose_does_not_block_others(test_settings):
    log: list[str] = []
    app = create_app(
        settings=test_settings,
        domains=[_closable_domain("first", log), _closable_domain("second", log, fail=True)],
    )
    async with LifespanManager(app):
        pass
    assert log == ["second", "first"]


async def test_bootstrap_failure_closes_already_bootstrapped(test_settings):
    log: list[str] = []

    async def broken(boot: BootstrapContext) -> object:
        raise RuntimeError("cannot connect")

    app = create_app(
        settings=test_settings,
        domains=[_closable_domain("first", log), _module("broken", bootstrap=broken)],
    )
    with pytest.raises(RuntimeError, match="cannot connect"):
        async with LifespanManager(app):
            pass
    assert log == ["first"]


async def test_duplicate_domain_type_is_rejected(test_settings):
    class Shared:
        pass

    async def bootstrap(boot: BootstrapContext) -> Shared:
        return Shared()

    app = create_app(
        settings=test_settings,
        domains=[_module("a", bootstrap=bootstrap), _module("b", bootstrap=bootstrap)],
    )
    with pytest.raises(TypeError, match="already registered"):
        async with LifespanManager(app):
            pass
