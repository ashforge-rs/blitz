"""Mis-wiring fails loudly instead of silently misbehaving."""

from unittest.mock import MagicMock

import pytest

from audit.backends.noop import NoopAuditBackend
from audit.integrity import NoIntegrity
from bootstrap import BootstrapContext
from config import Settings
from todo_app.auth.dependencies import current_principal
from todo_app.settings import from_boot


def test_bootstrap_without_todo_settings_names_the_fix() -> None:
    boot = BootstrapContext(
        settings=MagicMock(spec=Settings),
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
        extra={},
    )

    with pytest.raises(TypeError, match="create_todo_app"):
        from_boot(boot)


def test_protected_route_without_auth_provider_names_the_fix() -> None:
    # get_auth_context returns None when create_app() got no auth_provider.
    with pytest.raises(TypeError, match="create_todo_app"):
        current_principal(None)
