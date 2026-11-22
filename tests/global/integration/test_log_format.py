from typing import Any

import pytest

import lifespan


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(lifespan, "configure_logging", lambda **kwargs: calls.append(kwargs))
    return calls


async def test_logs_are_json_by_default(make_app, make_client, configured) -> None:
    async with make_client(make_app()):
        pass

    assert configured[0]["json"] is True


@pytest.mark.parametrize("environment", ["development", "production"])
async def test_text_logs_are_opt_in_in_any_environment(
    make_app, make_client, configured, environment: str
) -> None:
    app = make_app(settings={"LOG_FORMAT": "text", "ENVIRONMENT": environment})
    async with make_client(app):
        pass

    assert configured[0]["json"] is False


def test_an_unknown_format_is_refused(make_settings) -> None:
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        make_settings(LOG_FORMAT="xml")
