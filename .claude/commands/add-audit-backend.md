Implement a concrete `AuditBackend` for the persistence target described below.

Arguments: $ARGUMENTS

## Instructions

Create `src/audit/backends/<slug>.py` with a class extending `AuditBackend`:

```python
from audit.backend import AuditBackend, AuditEvent

class MyAuditBackend(AuditBackend):
    async def log(self, event: AuditEvent) -> None:
        ...
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
- Export the new class from `src/audit/backends/__init__.py`
- Use `from __future__ import annotations` at the top

### After implementation
1. Update `src/audit/backends/__init__.py` to export the new class
2. Write at least one test using a mock of the external dependency
3. Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
