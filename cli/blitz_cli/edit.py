"""Source edits located with ``ast``, applied as text so formatting and comments survive.

Every function takes and returns the whole module source. They insert code but never
re-indent or reorder it: ``project.tidy`` (Ruff isort + format) runs on edited files.
"""

import ast


class EditError(Exception):
    """The module does not have the shape the edit needs."""


def _offset(text: str, lineno: int, col: int) -> int:
    """Character offset of an ``ast`` (1-based line, UTF-8 byte column) position."""
    lines = text.splitlines(keepends=True)
    head = sum(len(line) for line in lines[: lineno - 1])
    return head + len(lines[lineno - 1].encode()[:col].decode())


def _line_start(text: str, lineno: int) -> int:
    return _offset(text, lineno, 0)


def _line_end(text: str, lineno: int) -> int:
    """Offset just past line ``lineno`` (including its newline)."""
    lines = text.splitlines(keepends=True)
    return sum(len(line) for line in lines[:lineno])


def _end(text: str, node: ast.expr | ast.stmt) -> int:
    return _offset(text, node.end_lineno or 0, node.end_col_offset or 0)


def parse(text: str, where: str = "module") -> ast.Module:
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        raise EditError(f"{where} does not parse: {exc}") from exc


# ── imports ──────────────────────────────────────────────────────────────────


def add_import(text: str, line: str) -> str:
    """Add a top-level import after the last module-level one (Ruff sorts and merges them)."""
    line = line.rstrip("\n")
    if any(existing.strip() == line for existing in text.splitlines()):
        return text
    imports = [n for n in parse(text).body if isinstance(n, ast.Import | ast.ImportFrom)]
    at = _line_end(text, imports[-1].end_lineno or 0) if imports else 0
    if not imports and text.startswith('"""'):  # keep a module docstring first
        doc = parse(text).body[0]
        at = _line_end(text, doc.end_lineno or 0)
        line = "\n" + line
    return text[:at] + line + "\n" + text[at:]


# ── calls ────────────────────────────────────────────────────────────────────


def _find_call(tree: ast.Module, func: str) -> ast.Call:
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == func
    ]
    if len(calls) != 1:
        raise EditError(f"expected one `{func}(...)` call, found {len(calls)}")
    return calls[0]


def add_call_kwarg(text: str, func: str, key: str, expr: str, *, to_list: bool = False) -> str:
    """Pass ``key=expr`` to the single ``func(...)`` call (``to_list``: append to ``key=[...]``)."""
    call = _find_call(parse(text), func)
    existing = next((k for k in call.keywords if k.arg == key), None)
    if existing is not None:
        if not to_list:
            raise EditError(f"`{func}(...)` already passes {key}=; change it by hand")
        if not isinstance(existing.value, ast.List):
            raise EditError(f"`{func}(..., {key}=...)` is not a list literal; add {expr} by hand")
        items = existing.value.elts
        if any(ast.unparse(item) == expr for item in items):
            return text
        close = _end(text, existing.value) - 1  # the `]`
        before = text[:close].rstrip()
        sep = "" if before.endswith(("[", ",")) else ", "
        return before + sep + expr + text[close:]
    value = f"[{expr}]" if to_list else expr
    close = _end(text, call) - 1  # the `)`
    before = text[:close].rstrip()
    has_args = bool(call.args or call.keywords)
    sep = (" " if before.endswith(",") else ", ") if has_args else ""
    return before + sep + f"{key}={value}" + text[close:]


# ── classes, functions, literals ─────────────────────────────────────────────


def find_class(tree: ast.Module, predicate: object) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and callable(predicate) and predicate(node):
            return node
    return None


def class_named(tree: ast.Module, name: str) -> ast.ClassDef | None:
    return find_class(tree, lambda c: c.name == name)


def method_names(cls: ast.ClassDef) -> set[str]:
    return {n.name for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def function_names(tree: ast.Module) -> set[str]:
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def append_to_class(text: str, class_name: str, code: str, *, blank_line: bool = True) -> str:
    """Append ``code`` (already indented for the class body) after the class's last line."""
    cls = class_named(parse(text), class_name)
    if cls is None:
        raise EditError(f"no class {class_name}")
    at = _line_end(text, cls.end_lineno or 0)
    gap = "\n" if blank_line else ""
    return text[:at] + gap + code.rstrip("\n") + "\n" + text[at:]


def _top_level_start(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return min([node.lineno, *(d.lineno for d in node.decorator_list)])


def insert_before_function(text: str, func: str, code: str) -> str:
    tree = parse(text)
    node = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == func
        ),
        None,
    )
    if node is None:
        raise EditError(f"no function {func}()")
    at = _line_start(text, _top_level_start(node))
    return text[:at] + code.rstrip("\n") + "\n\n\n" + text[at:]


def insert_after_assignment(text: str, name: str, code: str) -> str:
    """Insert ``code`` right after the module-level ``name = ...`` statement."""
    for node in parse(text).body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            at = _line_end(text, node.end_lineno or 0)
            return text[:at] + "\n\n" + code.rstrip("\n") + "\n" + text[at:]
    raise EditError(f"no module-level assignment to {name}")


def add_dict_entry(text: str, class_name: str, attr: str, entry: str) -> str:
    """Add ``entry`` (``"key: value"``) to the dict literal assigned to ``class_name.attr``."""
    cls = class_named(parse(text), class_name)
    if cls is None:
        raise EditError(f"no class {class_name}")
    target: ast.expr
    value: ast.expr | None
    for node in cls.body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == attr:
            if not isinstance(value, ast.Dict):
                raise EditError(f"{class_name}.{attr} is not a dict literal")
            close = _end(text, value) - 1  # the `}`
            before = text[:close].rstrip()
            sep = "" if before.endswith(("{", ",")) else ","
            indent = " " * (node.col_offset + 4)
            return before + sep + f"\n{indent}{entry},\n" + " " * node.col_offset + text[close:]
    raise EditError(f"no {class_name}.{attr}")


def insert_after_line(text: str, anchor: str, line: str) -> str:
    """Insert ``line`` after the first line whose stripped text is ``anchor``, same indent."""
    lines = text.splitlines(keepends=True)
    for i, existing in enumerate(lines):
        if existing.strip() == anchor:
            indent = existing[: len(existing) - len(existing.lstrip())]
            lines.insert(i + 1, f"{indent}{line}\n")
            return "".join(lines)
    raise EditError(f"no line `{anchor}`")


def insert_before_line(text: str, anchor: str, line: str) -> str:
    lines = text.splitlines(keepends=True)
    for i, existing in enumerate(lines):
        if existing.strip() == anchor:
            indent = existing[: len(existing) - len(existing.lstrip())]
            lines.insert(i, f"{indent}{line}\n")
            return "".join(lines)
    raise EditError(f"no line `{anchor}`")


def add_class_field(text: str, class_name: str, code: str) -> str:
    """Insert ``code`` (indented) after the last annotated field of ``class_name``."""
    cls = class_named(parse(text), class_name)
    if cls is None:
        raise EditError(f"no class {class_name}")
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    last = fields[-1] if fields else cls.body[-1]
    at = _line_end(text, last.end_lineno or 0)
    return text[:at] + "\n" + code.rstrip("\n") + "\n" + text[at:]


def add_to_all(text: str, name: str) -> str:
    """Add ``name`` to a module's ``__all__`` list literal, kept sorted (Ruff RUF022)."""
    for node in parse(text).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            names = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
            if name in names:
                return text
            entries = "".join(f'    "{n}",\n' for n in sorted({*map(str, names), name}))
            start = _line_start(text, node.lineno)
            end = _line_end(text, node.end_lineno or 0)
            return text[:start] + f"__all__ = [\n{entries}]\n" + text[end:]
    raise EditError("no `__all__ = [...]`")
