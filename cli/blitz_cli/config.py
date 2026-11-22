"""``[tool.blitz]`` in the project's ``pyproject.toml``: per-project generator defaults.

```toml
[tool.blitz]
templates = "templates"      # project templates; replace built-in ones file by file
default-service = "api"      # service new domains / providers are registered with
tests = true                 # generate tests (`--no-tests` / `--tests` override it)
```
"""

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .templates import TEMPLATES_DIR

if TYPE_CHECKING:
    from pathlib import Path

KEYS = {"templates": str, "default-service": str, "tests": bool}


class ConfigError(Exception):
    """``[tool.blitz]`` has an unknown key or a value of the wrong type."""


@dataclass(frozen=True, slots=True)
class BlitzConfig:
    templates: Path | None = None
    default_service: str = "api"
    tests: bool = True

    @property
    def template_dirs(self) -> list[Path]:
        return [TEMPLATES_DIR, *([self.templates] if self.templates else [])]


def load_config(root: Path) -> BlitzConfig:
    pyproject = root / "pyproject.toml"
    try:
        table = tomllib.loads(pyproject.read_text()).get("tool", {}).get("blitz", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{pyproject}: {exc}") from exc
    for key, value in table.items():
        expected = KEYS.get(key)
        if expected is None:
            raise ConfigError(f"[tool.blitz] unknown key {key!r} (known: {', '.join(KEYS)})")
        if not isinstance(value, expected):
            raise ConfigError(f"[tool.blitz] {key} must be a {expected.__name__}")
    templates = root / table["templates"] if "templates" in table else None
    if templates is not None and not templates.is_dir():
        raise ConfigError(f"[tool.blitz] templates: {templates} is not a directory")
    return BlitzConfig(
        templates=templates,
        default_service=table.get("default-service", "api"),
        tests=table.get("tests", True),
    )
