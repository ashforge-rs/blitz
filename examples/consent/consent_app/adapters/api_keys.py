"""API keys for the client systems that record consent (CRM, web app, call-centre tool).

Only a SHA-256 hash of each key is configured; a key carries 256 random bits, so
a fast hash is safe.  ``python -m consent_app.adapters.api_keys crm`` creates one.
"""

import hashlib
import re
import secrets
import sys

KEY_PREFIX = "csk_"
_CLIENT = re.compile(r"[a-z][a-z0-9_-]{1,63}")
_HASH = re.compile(r"[0-9a-f]{64}")


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def parse_api_keys(raw: str) -> dict[str, str]:
    """``crm=<sha256>,web=<sha256>`` → ``{sha256: client}``.  Raises on a malformed entry."""
    keys: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        client, _, digest = entry.partition("=")
        if not _CLIENT.fullmatch(client) or not _HASH.fullmatch(digest):
            msg = "CONSENT_API_KEYS entries must be client=<64 hex chars of sha256(key)>"
            raise ValueError(msg)
        keys[digest] = client
    return keys


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if not _CLIENT.fullmatch(name):
        sys.exit("usage: python -m consent_app.adapters.api_keys <client-name>")
    key = generate_key()
    print(f"API key for {name} (shown once; give it to that system):\n  {key}")
    print(f"Add to CONSENT_API_KEYS:\n  {name}={hash_key(key)}")
