"""The blitz project on disk: where domains and services live, and the service registries."""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_IMPORT = re.compile(r"^from domains\.(\w+) import domain as (\w+)\n", re.MULTILINE)
_LIST = re.compile(r"^DOMAINS\b[^=\n]*=\s*\[(?P<body>.*?)\]", re.MULTILINE | re.DOTALL)


class ProjectError(Exception):
    """The project layout is not what the command expects."""


def find_root(start: Path) -> Path:
    """The nearest directory at or above ``start`` with ``pyproject.toml`` and ``src/services/``."""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "services").is_dir():
            return candidate
    raise ProjectError(f"no blitz project (pyproject.toml + src/services/) at or above {start}")


@dataclass(frozen=True, slots=True)
class Project:
    root: Path

    @property
    def domains_dir(self) -> Path:
        return self.root / "src" / "domains"

    @property
    def services_dir(self) -> Path:
        return self.root / "src" / "services"

    def domains(self) -> list[str]:
        if not self.domains_dir.is_dir():
            return []
        return sorted(p.name for p in self.domains_dir.iterdir() if (p / "__init__.py").is_file())

    def services(self) -> list[str]:
        return sorted(p.name for p in self.services_dir.iterdir() if (p / "domains.py").is_file())

    def registry(self, service: str) -> Path:
        return self.services_dir / service / "domains.py"

    def registered(self, service: str) -> list[str]:
        """Domain packages imported by ``src/services/<service>/domains.py``, in file order."""
        path = self.registry(service)
        return [m.group(1) for m in _IMPORT.finditer(path.read_text())] if path.exists() else []

    def services_serving(self, domain: str) -> list[str]:
        return [s for s in self.services() if domain in self.registered(s)]

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    # ── registry edits ───────────────────────────────────────────────────────

    def register(self, service: str, domain: str) -> bool:
        """Add ``domain`` to the service's DOMAINS list. False if it was already there."""
        path = self.registry(service)
        if not path.exists():
            raise ProjectError(f"{self.rel(path)} not found")
        text = path.read_text()
        alias = f"{domain}_domain"
        import_line = f"from domains.{domain} import domain as {alias}\n"
        if import_line in text:
            return False
        listing = _LIST.search(text)
        if listing is None:
            raise ProjectError(f"no `DOMAINS = [...]` list in {self.rel(path)}")

        body = listing.group("body")
        if "\n" in body:  # multi-line: new entry before the closing bracket
            kept = body.rstrip()
            if (
                kept
                and not kept.endswith((",", "["))
                and not kept.splitlines()[-1].lstrip().startswith("#")
            ):
                kept += ","
            new_body = f"{kept}\n    {alias},\n"
        else:  # `[]` or `[a, b]`: rewrite one entry per line
            entries = [e.strip() for e in body.split(",") if e.strip()]
            new_body = "".join(f"\n    {e}," for e in [*entries, alias]) + "\n"
        text = text[: listing.start("body")] + new_body + text[listing.end("body") :]

        imports = list(_IMPORT.finditer(text))
        if imports:
            at = imports[-1].end()
        else:
            anchor = re.search(r"^(if TYPE_CHECKING:|DOMAINS:)", text, re.MULTILINE)
            at = anchor.start() if anchor else 0
            import_line += "\n"
        path.write_text(text[:at] + import_line + text[at:])
        return True

    def unregister(self, service: str, domain: str) -> bool:
        """Remove ``domain`` from the service's DOMAINS list. False if it was not there."""
        path = self.registry(service)
        text = path.read_text()
        match = next((m for m in _IMPORT.finditer(text) if m.group(1) == domain), None)
        if match is None:
            return False
        alias = match.group(2)
        text = text[: match.start()] + text[match.end() :]
        listing = _LIST.search(text)
        if listing is not None:
            body = listing.group("body")
            body = re.sub(rf"^[ \t]*{alias},?[ \t]*\n", "", body, flags=re.MULTILINE)
            body = re.sub(rf"\b{alias}\b,?\s*", "", body)
            text = text[: listing.start("body")] + body + text[listing.end("body") :]
        path.write_text(text)
        return True

    def remove_tree(self, path: Path) -> bool:
        if not path.exists():
            return False
        shutil.rmtree(path)
        return True


def tidy(root: Path, paths: list[Path]) -> str | None:
    """Sort imports and format generated Python files; return a warning or None."""
    py_files = [str(p) for p in paths if p.suffix == ".py" and p.exists()]
    if not py_files:
        return None
    ruff = [sys.executable, "-m", "ruff"]
    for args in (["check", "--fix", "--select", "I", "--quiet"], ["format", "--quiet"]):
        try:
            subprocess.run([*ruff, *args, *py_files], check=True, cwd=root)  # noqa: S603
        except (OSError, subprocess.CalledProcessError) as exc:
            return f"ruff {args[0]} failed ({exc}); run `make fmt`"
    return None
