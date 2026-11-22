"""Log messages are fixed lowercase phrases; values go in their own fields.

A message is what you group and search by, so it must not vary per call, and it must not hold
anything case-sensitive (IDs, paths, error text): those are fields, e.g.
``logger.info("domain bootstrapped", domain=name)``.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "todo_app"
LEVELS = {"trace", "debug", "info", "success", "warning", "error", "critical", "exception"}
LOGGERS = {"logger", "_logger"}


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute | ast.Call):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def _messages(tree: ast.AST) -> list[tuple[int, ast.expr | None]]:
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        method = node.func.attr
        if method not in LEVELS | {"log"} or _root_name(node.func.value) not in LOGGERS:
            continue
        index = 1 if method == "log" else 0
        found.append((node.lineno, node.args[index] if len(node.args) > index else None))
    return found


def _violations() -> list[str]:
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        for line, message in _messages(ast.parse(path.read_text(), filename=str(path))):
            where = f"{path.relative_to(SRC.parent)}:{line}"
            if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
                bad.append(f"{where}: message is not a string literal (put values in fields)")
            elif message.value != message.value.lower():
                bad.append(f"{where}: {message.value!r} is not lowercase")
    return bad


def test_log_messages_are_lowercase_literals() -> None:
    assert _violations() == []


@pytest.mark.parametrize(
    ("source", "ok"),
    [
        ('logger.info("domain bootstrapped", domain=name)', True),
        ('logger.bind(a=1).log(level, "audit")', True),
        ('logger.opt(exception=True).error("unhandled exception")', True),
        ('logger.info("Domain bootstrapped")', False),
        ('logger.error(f"{operation}.error")', False),
        ("logger.warning(message)", False),
    ],
)
def test_the_check_catches_what_it_should(source: str, ok: bool) -> None:
    [(_, message)] = _messages(ast.parse(source))
    is_ok = (
        isinstance(message, ast.Constant)
        and isinstance(message.value, str)
        and message.value == message.value.lower()
    )
    assert is_ok is ok
