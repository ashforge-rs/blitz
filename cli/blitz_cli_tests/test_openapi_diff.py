"""Breaking-change classification of OpenAPI documents."""

import copy

from blitz_cli.openapi_diff import diff


def _doc(**paths):
    return {
        "openapi": "3.1.0",
        "paths": paths,
        "components": {
            "schemas": {
                "Order": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "total": {"type": "number"},
                        "status": {"type": "string", "enum": ["open", "paid"]},
                    },
                    "required": ["id", "total", "status"],
                },
                "CreateOrder": {
                    "type": "object",
                    "properties": {"total": {"type": "number"}, "note": {"type": "string"}},
                    "required": ["total"],
                },
            }
        },
    }


def _ok(ref="#/components/schemas/Order"):
    return {"200": {"content": {"application/json": {"schema": {"$ref": ref}}}}}


BASE = _doc(
    **{
        "/v1/orders/{order_id}": {
            "get": {
                "parameters": [
                    {
                        "name": "order_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "expand",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "boolean"},
                    },
                ],
                "responses": _ok(),
            }
        },
        "/v1/orders/": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/CreateOrder"}}
                    },
                },
                "responses": {"201": _ok()["200"]},
            }
        },
    }
)


def _changes(mutate):
    new = copy.deepcopy(BASE)
    mutate(new)
    return {(c.breaking, c.operation, c.message) for c in diff(BASE, new)}


def _breaking(mutate):
    return {(op, msg) for breaking, op, msg in _changes(mutate) if breaking}


def test_identical_documents_have_no_changes():
    assert diff(BASE, copy.deepcopy(BASE)) == []


def test_removed_operation_is_breaking():
    assert ("GET /v1/orders/{order_id}", "operation removed") in _breaking(
        lambda d: d["paths"].pop("/v1/orders/{order_id}")
    )


def test_added_operation_is_not_breaking():
    def add(d):
        d["paths"]["/v1/orders/search"] = {"get": {"responses": _ok()}}

    assert _changes(add) == {(False, "GET /v1/orders/search", "operation added")}


def test_parameter_changes():
    def required(d):
        d["paths"]["/v1/orders/{order_id}"]["get"]["parameters"][1]["required"] = True

    def removed(d):
        d["paths"]["/v1/orders/{order_id}"]["get"]["parameters"].pop(1)

    def new_optional(d):
        d["paths"]["/v1/orders/{order_id}"]["get"]["parameters"].append(
            {"name": "page", "in": "query", "schema": {"type": "integer"}}
        )

    op = "GET /v1/orders/{order_id}"
    assert (op, "query parameter 'expand': now required") in _breaking(required)
    assert (op, "query parameter 'expand': removed") in _breaking(removed)
    assert _breaking(new_optional) == set()


def test_request_body_changes():
    schema = lambda d: d["components"]["schemas"]["CreateOrder"]  # noqa: E731
    op = "POST /v1/orders/"
    assert (op, "request body.note: now required") in _breaking(
        lambda d: schema(d)["required"].append("note")
    )

    def new_required(d):
        schema(d)["properties"]["currency"] = {"type": "string"}
        schema(d)["required"].append("currency")

    assert (op, "request body.currency: added as required") in _breaking(new_required)

    def narrower(d):
        schema(d)["properties"]["total"] = {"type": "integer"}

    assert (op, "request body.total: no longer accepts number") in _breaking(narrower)


def test_widening_a_request_type_is_not_breaking():
    def wider(d):
        d["components"]["schemas"]["CreateOrder"]["properties"]["note"] = {
            "anyOf": [{"type": "string"}, {"type": "null"}]
        }

    assert _breaking(wider) == set()


def test_response_changes():
    order = lambda d: d["components"]["schemas"]["Order"]  # noqa: E731
    op = "GET /v1/orders/{order_id}"
    assert (op, "response 200.status: removed") in _breaking(
        lambda d: order(d)["properties"].pop("status")
    )
    assert (op, "response 200.total: may now be absent") in _breaking(
        lambda d: order(d)["required"].remove("total")
    )

    def nullable(d):
        order(d)["properties"]["total"] = {"anyOf": [{"type": "number"}, {"type": "null"}]}

    assert (op, "response 200.total: may now be null") in _breaking(nullable)

    def new_enum_value(d):
        order(d)["properties"]["status"]["enum"].append("refunded")

    assert (op, "response 200.status: may now return ['refunded']") in _breaking(new_enum_value)

    def extra_field(d):
        order(d)["properties"]["currency"] = {"type": "string"}

    assert _breaking(extra_field) == set()


def test_integer_to_number_in_a_response_is_breaking_but_not_the_reverse():
    def to_integer(d):
        d["components"]["schemas"]["Order"]["properties"]["total"] = {"type": "integer"}

    assert _breaking(to_integer) == set()  # integers are numbers


def test_removed_success_status_is_breaking():
    op = "POST /v1/orders/"
    assert (op, "response 201: removed") in _breaking(
        lambda d: d["paths"]["/v1/orders/"]["post"].update(responses={"202": _ok()["200"]})
    )


def test_recursive_schemas_terminate():
    node = {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Node"}}}
    doc = {
        "paths": {
            "/n": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {"schemas": {"Node": node}},
    }
    assert diff(doc, copy.deepcopy(doc)) == []


def test_tighter_request_values_are_breaking_looser_are_not():
    note = lambda d: d["components"]["schemas"]["CreateOrder"]["properties"]["note"]  # noqa: E731
    op = "POST /v1/orders/"

    def limit(value):
        return lambda d: note(d).update(maxLength=value)

    assert (op, "request body.note: maxLength none → 10") in _breaking(limit(10))
    tighter = copy.deepcopy(BASE)
    limit(100)(tighter)
    narrower = copy.deepcopy(tighter)
    limit(10)(narrower)
    assert [(c.breaking, c.message) for c in diff(tighter, narrower)] == [
        (True, "request body.note: maxLength 100 → 10")
    ]
    assert [c.breaking for c in diff(narrower, tighter)] == [False]  # raised: looser
    assert (op, "request body.note: pattern none → '^[a-z]+$'") in _breaking(
        lambda d: note(d).update(pattern="^[a-z]+$")
    )
    assert (op, "request body.total: minimum none → 0") in _breaking(
        lambda d: d["components"]["schemas"]["CreateOrder"]["properties"]["total"].update(minimum=0)
    )


def test_constraints_on_an_optional_value_are_compared():
    def optional(max_length):
        def mutate(d):
            d["components"]["schemas"]["CreateOrder"]["properties"]["note"] = {
                "anyOf": [{"type": "string", "maxLength": max_length}, {"type": "null"}]
            }

        return mutate

    old, new = copy.deepcopy(BASE), copy.deepcopy(BASE)
    optional(255)(old)
    optional(20)(new)
    assert [(c.breaking, c.message) for c in diff(old, new)] == [
        (True, "request body.note: maxLength 255 → 20")
    ]


def test_closing_a_request_object_is_breaking():
    schema = lambda d: d["components"]["schemas"]["CreateOrder"]  # noqa: E731
    op = "POST /v1/orders/"
    assert (op, "request body: no longer accepts extra properties") in _breaking(
        lambda d: schema(d).update(additionalProperties=False)
    )
    closed = copy.deepcopy(BASE)
    schema(closed)["additionalProperties"] = False
    without_note = copy.deepcopy(closed)
    schema(without_note)["properties"].pop("note")
    assert [(c.breaking, c.message) for c in diff(closed, without_note)] == [
        (True, "request body.note: removed (now rejected)")
    ]


def test_response_constraints_are_not_breaking():
    def limit(d):
        d["components"]["schemas"]["Order"]["properties"]["id"]["maxLength"] = 36

    assert _breaking(limit) == set()
    assert (False, "GET /v1/orders/{order_id}", "response 200.id: maxLength none → 36") in (
        _changes(limit)
    )
