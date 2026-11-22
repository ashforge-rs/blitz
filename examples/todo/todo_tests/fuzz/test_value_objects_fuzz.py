"""Property tests for the core's value objects and token functions."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from todo_app.todos.entities import Title
from todo_app.users.entities import (
    DisplayName,
    EmailAddress,
    generate_token,
    hash_token,
    looks_like_token,
)

_local = st.text(st.characters(categories=["L", "N"], include_characters="._+-"), min_size=1)
_domain = st.from_regex(r"[a-z0-9]{1,20}\.[a-z]{2,6}", fullmatch=True)
emails = st.builds(lambda local, domain: f"{local}@{domain}", _local, _domain).filter(
    lambda e: len(e.strip().lower()) <= EmailAddress.MAX_LENGTH
)
padding = st.text(" \t\n", max_size=3)


@given(email=emails, left=padding, right=padding)
def test_email_normalisation_is_idempotent_and_padding_insensitive(
    email: str, left: str, right: str
) -> None:
    once = EmailAddress(left + email + right)

    assert EmailAddress(once.value) == once
    assert once == EmailAddress(email.upper() if email.isascii() else email)


@given(st.text(max_size=300))
def test_title_accepts_exactly_the_trimmed_lengths_in_range(raw: str) -> None:
    trimmed = raw.strip()
    if 1 <= len(trimmed) <= Title.MAX_LENGTH:
        assert Title(raw).value == trimmed
    else:
        with pytest.raises(ValueError, match="characters"):
            Title(raw)


@given(st.text(max_size=150))
def test_display_name_never_holds_surrounding_whitespace(raw: str) -> None:
    try:
        name = DisplayName(raw)
    except ValueError:
        return
    assert name.value == name.value.strip()
    assert 1 <= len(name.value) <= DisplayName.MAX_LENGTH


@given(st.text())
def test_arbitrary_text_is_never_mistaken_for_a_token_unless_prefixed(raw: str) -> None:
    assert looks_like_token(raw) == (raw.startswith("tdo_") and len(raw) > len("tdo_"))


@given(st.text(), st.text())
def test_token_hash_is_deterministic_and_distinguishes_inputs(a: str, b: str) -> None:
    assert hash_token(a) == hash_token(a)
    if a != b:
        assert hash_token(a) != hash_token(b)


def test_generated_tokens_always_pass_the_pre_check() -> None:
    assert all(looks_like_token(generate_token()) for _ in range(200))
