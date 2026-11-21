from todo_app.users.entities import TOKEN_PREFIX, generate_token, hash_token, looks_like_token


def test_generated_tokens_are_prefixed_and_unique() -> None:
    tokens = {generate_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(t.startswith(TOKEN_PREFIX) for t in tokens)


def test_token_carries_256_bits() -> None:
    # token_urlsafe(32): 32 random bytes → 43 base64url characters.
    assert len(generate_token()) == len(TOKEN_PREFIX) + 43


def test_hash_is_hex_sha256_and_not_the_token() -> None:
    token = generate_token()

    assert len(hash_token(token)) == 64
    assert token not in hash_token(token)


def test_looks_like_token() -> None:
    assert looks_like_token(generate_token())
    assert not looks_like_token(TOKEN_PREFIX)
    assert not looks_like_token("ghp_something")
    assert not looks_like_token("")
