"""API tokens: random, shown to the user once, stored only as a SHA-256 hash.

A slow password hash (bcrypt, argon2) isn't needed here.  A token carries 256
random bits, so its hash can't be brute-forced, and a fast deterministic hash
lets authentication find the token through an indexed column.
"""

import hashlib
import secrets

#: Makes tokens recognisable, e.g. to secret scanners and in support requests.
TOKEN_PREFIX = "tdo_"  # noqa: S105 — public prefix, not a secret


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_token(value: str) -> bool:
    """Cheap pre-check so malformed credentials never reach storage."""
    return value.startswith(TOKEN_PREFIX) and len(value) > len(TOKEN_PREFIX)
