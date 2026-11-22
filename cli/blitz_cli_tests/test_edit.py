"""Source edits: new items go after the last element, so trailing comments cannot swallow them."""

import ast

import pytest

from blitz_cli.edit import EditError, _lines, add_call_kwarg, add_dict_entry, insert_after_line


def _ok(text: str) -> str:
    ast.parse(text)
    return text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("app = create_app()\n", "app = create_app(x=1)\n"),
        ("app = create_app(a=1)\n", "app = create_app(a=1, x=1)\n"),
        ("app = create_app(a=1,)\n", "app = create_app(a=1, x=1,)\n"),
        (
            "app = create_app(\n    a=1,  # keep\n)\n",
            "app = create_app(\n    a=1,  # keep\n    x=1,\n)\n",
        ),
        (
            "app = create_app(\n    a=1  # keep\n)\n",
            "app = create_app(\n    a=1,  # keep\n    x=1,\n)\n",
        ),
        ("app = create_app(  # why\n)\n", "app = create_app(  # why\nx=1)\n"),
    ],
)
def test_add_call_kwarg(source, expected):
    assert _ok(add_call_kwarg(source, "create_app", "x", "1")) == expected


def test_add_to_a_kwarg_list_with_a_comment():
    source = "app = create_app(\n    checks=[\n        a,  # db\n    ],\n)\n"
    out = _ok(add_call_kwarg(source, "create_app", "checks", "b", to_list=True))
    assert "        a,  # db\n        b,\n    ],\n" in out
    assert _ok(add_call_kwarg("create_app(checks=[])\n", "create_app", "checks", "b", to_list=True))
    assert add_call_kwarg(out, "create_app", "checks", "b", to_list=True) == out  # once


def test_add_dict_entry_keeps_the_comment_on_its_entry():
    source = "class E:\n    STATUS = {\n        A: 404  # not found\n    }\n"
    out = _ok(add_dict_entry(source, "E", "STATUS", "B: 409"))
    assert "        A: 404,  # not found\n        B: 409,\n    }\n" in out
    empty = _ok(add_dict_entry("class E:\n    STATUS = {}\n", "E", "STATUS", "B: 409"))
    assert "    STATUS = {\n        B: 409,\n    }\n" in empty
    with pytest.raises(EditError):
        add_dict_entry(source, "E", "MISSING", "B: 409")


def test_lines_split_like_the_tokenizer():
    text = 'x = "a\x0cb\u2028c"\ny = 1\n'
    assert _lines(text) == ['x = "a\x0cb\u2028c"\n', "y = 1\n"]
    out = _ok(insert_after_line(text, "y = 1", "z = 2"))
    assert out.endswith("y = 1\nz = 2\n")
    source = 'x = "\x0c"\napp = create_app(a=1)\n'
    assert add_call_kwarg(source, "create_app", "x", "1").endswith("create_app(a=1, x=1)\n")
