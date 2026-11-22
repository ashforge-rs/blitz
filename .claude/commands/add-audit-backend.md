Implement a concrete `AuditBackend` for the persistence target described below.

Arguments: $ARGUMENTS

## Start with the generator

Do not create the files by hand:

```bash
uv run --project cli blitz g audit <slug> --dry-run   # see what changes
uv run --project cli blitz g audit <slug>
```

It creates `src/audit/backends/<slug>.py` (a `<Slug>AuditBackend` that forwards to Loguru
until `log()` writes to the target) and `tests/global/unit/test_audit_<slug>.py`, and passes
`audit_backend=<Slug>AuditBackend()` to `create_app()` in the service's `main.py`. Then write
the events to the target as described below.

## Instructions

The generated `src/audit/backends/<slug>.py` holds a class extending `AuditBackend`; fill in:

```python
from audit.backend import AuditBackend, AuditEvent


class MyAuditBackend(AuditBackend):
    async def log(self, event: AuditEvent) -> None: ...
```

### AuditEvent fields available
| Field | Type | Notes |
|---|---|---|
| `request_id` | `str` | UUID4 hex |
| `method` | `str` | HTTP verb |
| `path` | `str` | URL path |
| `status_code` | `int` | HTTP status |
| `duration_ms` | `float` | Wall time |
| `ip` | `str` | Client IP |
| `principal` | `Any` | Set by auth dependency, else `None` |
| `extra` | `dict` | Arbitrary extra fields |
| `timestamp` | `datetime` | UTC |

### Rules
- `log()` must never raise — catch all exceptions internally and log them via Loguru (`from loguru import logger`)
- If the backend requires external I/O (DB, HTTP, queue) it should be initialised in `__init__` or a separate `connect()` coroutine and closed gracefully
- If a connection is needed, hook into lifespan by documenting that the consumer should call `await backend.connect()` during startup and `await backend.close()` during shutdown
- The generator exports the class from `src/audit/backends/__init__.py`
- No `from __future__ import annotations` — Python 3.14+ evaluates annotations lazily (PEP 649)

### After implementation
1. Check the export in `src/audit/backends/__init__.py` and the `audit_backend=` wiring in `main.py`
2. Write at least one test using a mock of the external dependency
3. Run `make fmt && make verify` — `make verify` must exit 0
