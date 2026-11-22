"""Compare two OpenAPI documents and classify each change as breaking or not.

Breaking means an existing client can stop working:

- an operation, a response status (2xx) or a parameter is removed;
- a parameter or a request-body property becomes required, or a request body appears
  as required;
- a request accepts fewer types or enum values than before;
- a response drops a property, may now omit one it always had, or returns types or
  enum values it never did.

Everything else (new operations, optional parameters, extra response fields) is listed
as non-breaking. ``$ref`` are resolved inside each document; recursion is bounded.
"""

from dataclasses import dataclass
from typing import Any

METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
_MAX_DEPTH = 12


@dataclass(frozen=True, slots=True)
class Change:
    breaking: bool
    operation: str  # "POST /v1/orders" or "" for document-level
    message: str


class _Doc:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document

    def resolve(self, schema: Any) -> dict[str, Any]:
        seen: set[str] = set()
        while isinstance(schema, dict) and "$ref" in schema:
            ref = str(schema["$ref"])
            if ref in seen or not ref.startswith("#/"):
                return {}
            seen.add(ref)
            node: Any = self.document
            for part in ref[2:].split("/"):
                node = (
                    node.get(part.replace("~1", "/").replace("~0", "~"), {})
                    if isinstance(node, dict)
                    else {}
                )
            schema = node
        return schema if isinstance(schema, dict) else {}


def _types(doc: _Doc, schema: dict[str, Any]) -> set[str]:
    """The JSON types a schema admits ("any" when unconstrained)."""
    schema = doc.resolve(schema)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            found: set[str] = set()
            for member in schema[key]:
                found |= _types(doc, member)
            return found
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _types(doc, schema["allOf"][0])
    kind = schema.get("type")
    if isinstance(kind, list):
        return {str(k) for k in kind}
    if kind:
        return {str(kind)}
    if "properties" in schema:
        return {"object"}
    return {"any"}


def _uncovered(types: set[str], by: set[str]) -> set[str]:
    """``types`` that ``by`` does not admit (``number`` admits ``integer``)."""
    covered = by | ({"integer"} if "number" in by else set())
    return types - covered


def _object_part(doc: _Doc, schema: dict[str, Any]) -> dict[str, Any]:
    """The object member of a schema (through anyOf/oneOf with null, allOf of one)."""
    schema = doc.resolve(schema)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            objects = [doc.resolve(m) for m in schema[key] if "object" in _types(doc, m)]
            return objects[0] if len(objects) == 1 else {}
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _object_part(doc, schema["allOf"][0])
    return schema


class _Comparer:
    def __init__(self, old: dict[str, Any], new: dict[str, Any]) -> None:
        self.old, self.new = _Doc(old), _Doc(new)
        self.changes: list[Change] = []

    def add(self, breaking: bool, operation: str, message: str) -> None:
        self.changes.append(Change(breaking, operation, message))

    # ── schemas ──────────────────────────────────────────────────────────────

    def schema(
        self, op: str, where: str, old: Any, new: Any, *, request: bool, depth: int = 0
    ) -> None:
        if depth > _MAX_DEPTH:
            return
        o, n = self.old.resolve(old), self.new.resolve(new)
        o_types, n_types = _types(self.old, o), _types(self.new, n)
        if "any" not in o_types and "any" not in n_types and o_types != n_types:
            if request:
                lost = _uncovered(o_types, n_types)
                if lost:
                    self.add(True, op, f"{where}: no longer accepts {', '.join(sorted(lost))}")
                else:
                    self.add(
                        False, op, f"{where}: also accepts {', '.join(sorted(n_types - o_types))}"
                    )
            else:
                gained = _uncovered(n_types, o_types)
                if gained:
                    self.add(True, op, f"{where}: may now be {', '.join(sorted(gained))}")
                else:
                    self.add(
                        False, op, f"{where}: no longer {', '.join(sorted(o_types - n_types))}"
                    )

        o_enum, n_enum = o.get("enum"), n.get("enum")
        if isinstance(o_enum, list) and isinstance(n_enum, list):
            removed = [v for v in o_enum if v not in n_enum]
            added = [v for v in n_enum if v not in o_enum]
            if request and removed:
                self.add(True, op, f"{where}: no longer accepts {removed}")
            if not request and added:
                self.add(True, op, f"{where}: may now return {added}")
            if (request and added) or (not request and removed):
                self.add(False, op, f"{where}: enum now {n_enum}")

        o_obj, n_obj = _object_part(self.old, o), _object_part(self.new, n)
        o_props, n_props = o_obj.get("properties", {}), n_obj.get("properties", {})
        if isinstance(o_props, dict) and isinstance(n_props, dict) and (o_props or n_props):
            o_req, n_req = set(o_obj.get("required", [])), set(n_obj.get("required", []))
            for name in sorted(o_props.keys() | n_props.keys()):
                field = f"{where}.{name}"
                if name not in n_props:
                    if request:
                        self.add(False, op, f"{field}: removed (now ignored)")
                    else:
                        self.add(True, op, f"{field}: removed")
                elif name not in o_props:
                    if request and name in n_req:
                        self.add(True, op, f"{field}: added as required")
                    else:
                        self.add(False, op, f"{field}: added")
                else:
                    if request and name in n_req and name not in o_req:
                        self.add(True, op, f"{field}: now required")
                    if not request and name in o_req and name not in n_req:
                        self.add(True, op, f"{field}: may now be absent")
                    self.schema(
                        op, field, o_props[name], n_props[name], request=request, depth=depth + 1
                    )

        if "array" in o_types & n_types and "items" in o and "items" in n:
            self.schema(op, f"{where}[]", o["items"], n["items"], request=request, depth=depth + 1)

    # ── operations ───────────────────────────────────────────────────────────

    def parameters(self, op: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        def index(
            doc: _Doc, operation: dict[str, Any], path_item: dict[str, Any]
        ) -> dict[tuple[str, str], dict[str, Any]]:
            found = {}
            for param in [*path_item.get("parameters", []), *operation.get("parameters", [])]:
                param = doc.resolve(param)
                found[(str(param.get("in")), str(param.get("name")))] = param
            return found

        o_params = index(self.old, old["op"], old["item"])
        n_params = index(self.new, new["op"], new["item"])
        for key in sorted(o_params.keys() | n_params.keys()):
            label = f"{key[0]} parameter {key[1]!r}"
            if key not in n_params:
                self.add(True, op, f"{label}: removed")
            elif key not in o_params:
                required = bool(n_params[key].get("required"))
                self.add(required, op, f"{label}: added{' as required' if required else ''}")
            else:
                if n_params[key].get("required") and not o_params[key].get("required"):
                    self.add(True, op, f"{label}: now required")
                self.schema(
                    op,
                    label,
                    o_params[key].get("schema", {}),
                    n_params[key].get("schema", {}),
                    request=True,
                )

    def body(self, op: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        o_body = self.old.resolve(old.get("requestBody", {}))
        n_body = self.new.resolve(new.get("requestBody", {}))
        if not n_body:
            if o_body:
                self.add(False, op, "request body: removed (now ignored)")
            return
        if not o_body:
            required = bool(n_body.get("required"))
            self.add(required, op, f"request body: added{' as required' if required else ''}")
            return
        if n_body.get("required") and not o_body.get("required"):
            self.add(True, op, "request body: now required")
        o_json = o_body.get("content", {}).get("application/json", {}).get("schema")
        n_json = n_body.get("content", {}).get("application/json", {}).get("schema")
        if o_json is not None and n_json is not None:
            self.schema(op, "request body", o_json, n_json, request=True)

    def responses(self, op: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        o_resp, n_resp = old.get("responses", {}), new.get("responses", {})
        for status in sorted(o_resp.keys() | n_resp.keys()):
            success = status.startswith("2")
            if status not in n_resp:
                self.add(success, op, f"response {status}: removed")
                continue
            if status not in o_resp:
                self.add(False, op, f"response {status}: added")
                continue
            o_json = (
                self.old.resolve(o_resp[status])
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            n_json = (
                self.new.resolve(n_resp[status])
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if success and o_json is not None and n_json is not None:
                self.schema(op, f"response {status}", o_json, n_json, request=False)

    def run(self) -> list[Change]:
        def operations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
            found = {}
            for path, item in document.get("paths", {}).items():
                for method in METHODS:
                    if method in item:
                        found[f"{method.upper()} {path}"] = {"op": item[method], "item": item}
            return found

        o_ops, n_ops = operations(self.old.document), operations(self.new.document)
        for name in sorted(o_ops.keys() | n_ops.keys()):
            if name not in n_ops:
                self.add(True, name, "operation removed")
            elif name not in o_ops:
                self.add(False, name, "operation added")
            else:
                self.parameters(name, o_ops[name], n_ops[name])
                self.body(name, o_ops[name]["op"], n_ops[name]["op"])
                self.responses(name, o_ops[name]["op"], n_ops[name]["op"])
        return self.changes


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    return _Comparer(old, new).run()
