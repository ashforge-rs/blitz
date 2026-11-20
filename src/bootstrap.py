"""
The domain-module contract: what ``create_app(domains=[...])`` accepts.

A domain module is a plain Python module (usually ``domains/<name>/domain.py``)
exposing any of these hooks:

``make_router() -> APIRouter``
    Called once by :func:`app.create_app`; the router is mounted under
    ``settings.API_PREFIX``.

``async bootstrap(boot: BootstrapContext) -> object``
    Called during lifespan startup.  Open pools / clients here and return the
    domain instance; resolve it later with :func:`state.get_domain`.  If the
    instance has an ``async aclose()`` method it is awaited on shutdown (after
    in-flight requests drain), in reverse bootstrap order.

``register_exception_handlers(app: FastAPI) -> None``
    Optional, for domain-specific exception handlers.  Not needed for
    :class:`errors.domain.DomainError` failures — those are handled globally.

:func:`validate_domain_module` checks the contract when the app is created so
that a typo (``make_routers``) or a stale signature fails at import time instead
of silently mounting nothing.
"""

import inspect
from annotationlib import Format
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import types
    from collections.abc import Mapping

    from audit.backend import AuditBackend, AuditIntegrity
    from config import Settings

HOOKS = ("make_router", "bootstrap", "register_exception_handlers")


@dataclass(frozen=True, slots=True)
class BootstrapContext:
    """Framework singletons handed to every domain's ``bootstrap()``."""

    settings: Settings
    audit_backend: AuditBackend
    audit_integrity: AuditIntegrity
    #: The ``extra_context`` passed to ``create_app()`` (DB pools, clients, …).
    extra: Mapping[str, Any] = field(default_factory=dict)


def validate_domain_module(module: types.ModuleType) -> None:
    """Raise ``TypeError`` if *module* does not satisfy the domain contract."""
    name = module.__name__
    present = [hook for hook in HOOKS if hasattr(module, hook)]
    if not present:
        msg = f"domain module {name!r} exposes none of {', '.join(HOOKS)}"
        raise TypeError(msg)

    for hook in present:
        if not callable(getattr(module, hook)):
            msg = f"{name}.{hook} must be callable"
            raise TypeError(msg)

    bootstrap = getattr(module, "bootstrap", None)
    if bootstrap is not None:
        if not inspect.iscoroutinefunction(bootstrap):
            msg = f"{name}.bootstrap must be an async function"
            raise TypeError(msg)
        # FORWARDREF: don't evaluate annotations (they are often TYPE_CHECKING-only).
        signature = inspect.signature(bootstrap, annotation_format=Format.FORWARDREF)
        params = list(signature.parameters.values())
        positional = [
            p
            for p in params
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
        ]
        if len(positional) != 1:
            msg = (
                f"{name}.bootstrap must take exactly one argument (boot: BootstrapContext), "
                f"got ({', '.join(p.name for p in params)})"
            )
            raise TypeError(msg)
