"""Agent-facing docs only reference files and make targets that exist.

Stale instructions are worse than none: an agent follows them confidently.
Placeholders (``<name>``, ``{domain}``, ``*``, ``$x``) and the illustrative
``orders`` domain used throughout the docs are skipped.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted(
    [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        *ROOT.glob(".claude/commands/**/*.md"),
        *ROOT.glob(".claude/skills/*/SKILL.md"),
        *ROOT.glob(".github/agents/*.md"),
    ]
)
TOP_LEVEL = (
    "src/",
    "tests/",
    "scripts/",
    ".github/",
    ".claude/",
    "grafana/",
    "infra/",
    "openspec/",
    "docs/",
    "examples/",
    "cli/",
)
ROOT_FILES = {"Makefile", "pyproject.toml", ".env.example", "docker-compose.yml", "AGENTS.md"}
PLACEHOLDER = re.compile(r"[<>{}*$]|\.\.\.|…")
EXAMPLE_NAMES = re.compile(r"\b(orders?|users?|billing|worker|people|my_\w+|foo|bar)\b")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
MAKE_TARGET = re.compile(r"\bmake ([a-z][a-z0-9-]*)")
LINE_SUFFIX = re.compile(r":\d+$")
# Paths that docs tell the agent to create, so they don't exist in a fresh clone.
CREATED_BY_INSTRUCTIONS = {
    "src/auth/provider.py",  # starting-point skill, auth step
    "openspec/changes",  # created by the first `openspec-propose`
}


def _referenced_paths(text: str) -> set[str]:
    paths = set()
    for span in CODE_SPAN.findall(text):
        for token in span.split():
            token = LINE_SUFFIX.sub("", token.strip("`'\",;:()").split("::")[0])
            is_path = token in ROOT_FILES or token.startswith(TOP_LEVEL)
            if is_path and not PLACEHOLDER.search(token) and not EXAMPLE_NAMES.search(token):
                paths.add(token.rstrip("/"))
    return paths


def _code_blocks(text: str) -> list[str]:
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


def _make_targets() -> set[str]:
    makefile = (ROOT / "Makefile").read_text()
    return set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_referenced_paths_exist(doc: Path) -> None:
    paths = _referenced_paths(doc.read_text()) - CREATED_BY_INSTRUCTIONS
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert missing == [], f"{doc.relative_to(ROOT)} references missing paths"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_referenced_make_targets_exist(doc: Path) -> None:
    targets = _make_targets()
    spans = CODE_SPAN.findall(doc.read_text()) + _code_blocks(doc.read_text())
    used = {target for span in spans for target in MAKE_TARGET.findall(span)}
    assert sorted(used - targets) == [], f"{doc.relative_to(ROOT)} uses unknown make targets"
