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


@pytest.mark.parametrize(("raw", "expected"), [("/v1", "/v1"), ("/v2/", "/v2"), ("", "")])
def test_api_prefix_normalised(raw, expected):
    assert expected == Settings(_env_file=None, API_PREFIX=raw).API_PREFIX


def test_api_prefix_requires_leading_slash():
    with pytest.raises(ValueError, match="API_PREFIX"):
        Settings(_env_file=None, API_PREFIX="v1")


def test_env_example_documents_every_setting():
    """Every Settings field appears in .env.example (set or commented out), and nothing stale."""
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / ".env.example").read_text()
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))
    compose_only = {name for name in documented if name.startswith("GF_")}
    fields = set(Settings.model_fields)
    assert fields - documented == set(), "add these to .env.example"
    assert documented - fields - compose_only == set(), "remove these from .env.example"


def test_port_is_validated():
    with pytest.raises(ValueError, match="PORT"):
        Settings(_env_file=None, PORT=0)  # type: ignore[call-arg]
