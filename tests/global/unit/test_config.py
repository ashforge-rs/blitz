from __future__ import annotations

import pytest

from config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.0.0.0/8,172.16.0.0/12", ["10.0.0.0/8", "172.16.0.0/12"]),
        (" a.com , b.com ,", ["a.com", "b.com"]),
        ('["a.com", "b.com"]', ["a.com", "b.com"]),
        ("", []),
    ],
)
def test_list_settings_parse_from_env(monkeypatch, raw, expected):
    for name in ("TRUSTED_PROXIES", "ALLOWED_HOSTS", "OPENAPI_SERVERS"):
        monkeypatch.setenv(name, raw)
    settings = Settings(_env_file=None)
    assert expected == settings.TRUSTED_PROXIES
    assert expected == settings.ALLOWED_HOSTS
    assert expected == settings.OPENAPI_SERVERS


def test_allowed_origins_from_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example,https://b.example")
    assert Settings(_env_file=None).ALLOWED_ORIGINS == ["https://a.example", "https://b.example"]


def test_cors_credentials_with_wildcard_rejected():
    with pytest.raises(ValueError, match="CORS_ALLOW_CREDENTIALS"):
        Settings(_env_file=None, CORS_ALLOW_CREDENTIALS=True, ALLOWED_ORIGINS=["*"])
