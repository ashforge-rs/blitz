"""Template sets: directories of ``*.tmpl`` files rendered with ``string.Template``.

A set lives in ``blitz_cli/templates/<set>/`` and mirrors the project layout. Both file
paths and contents use ``$placeholders`` (``$$`` for a literal ``$``); the ``.tmpl``
suffix is dropped on render. ``template.toml`` holds the set's ``description``.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SUFFIX = ".tmpl"
MANIFEST = "template.toml"


class TemplateError(Exception):
    """A template set is missing, or a placeholder has no value."""


@dataclass(frozen=True, slots=True)
class RenderedFile:
    path: Path  # relative to the project root
    content: str


@dataclass(frozen=True, slots=True)
class TemplateSet:
    name: str
    directory: Path
    description: str

    def sources(self) -> list[Path]:
        """Template files, relative to the set's directory, in a stable order."""
        return sorted(p.relative_to(self.directory) for p in self.directory.rglob(f"*{SUFFIX}"))

    def placeholders(self) -> set[str]:
        names: set[str] = set()
        for source in self.sources():
            for text in (str(source), (self.directory / source).read_text()):
                names.update(Template(text).get_identifiers())
        return names

    def render(self, values: dict[str, str]) -> list[RenderedFile]:
        rendered = []
        for source in self.sources():
            content = (self.directory / source).read_text()
            path = str(source).removesuffix(SUFFIX)
            try:
                rendered.append(
                    RenderedFile(Path(_substitute(path, values)), _substitute(content, values))
                )
            except KeyError as exc:
                raise TemplateError(f"{self.name}/{source}: no value for ${exc.args[0]}") from exc
        return rendered


def _substitute(text: str, values: dict[str, str]) -> str:
    return Template(text).substitute(values)


def available(directory: Path = TEMPLATES_DIR) -> list[TemplateSet]:
    sets = []
    for path in sorted(p for p in directory.iterdir() if p.is_dir()):
        manifest = path / MANIFEST
        meta = tomllib.loads(manifest.read_text()) if manifest.exists() else {}
        sets.append(TemplateSet(path.name, path, str(meta.get("description", ""))))
    return sets


def load(name: str, directory: Path = TEMPLATES_DIR) -> TemplateSet:
    for template_set in available(directory):
        if template_set.name == name:
            return template_set
    known = ", ".join(t.name for t in available(directory))
    raise TemplateError(f"unknown template set {name!r} (available: {known})")
