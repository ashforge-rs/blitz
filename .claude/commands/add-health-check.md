Add a new readiness health check for the dependency described below.

Arguments: $ARGUMENTS

## Instructions

A health check is an `async` callable with no required arguments that returns a `dict` with at least:
- `"name"`: `str` — unique identifier shown in `GET /health` response
- `"healthy"`: `bool` — `True` = dependency is reachable

It can include any additional diagnostic keys (latency, version, etc.).

### Pattern

```python
async def check_<name>() -> dict:
    try:
        # probe the dependency
        return {"name": "<name>", "healthy": True}
    except Exception as exc:
        return {"name": "<name>", "healthy": False, "error": str(exc)}
```

### Where to put it

- If the check is self-contained (no shared client), add it to `src/blitz/routes/health.py` or a new `src/blitz/checks/<name>.py`
- If it needs a shared client (DB pool, Redis, etc.) stored on `app.state`, accept the client as a closure argument:

```python
def make_db_check(db) -> Callable:
    async def check() -> dict:
        ok = await db.ping()
        return {"name": "database", "healthy": ok}
    return check

# then in app setup:
create_app(health_checks=[make_db_check(db_pool)])
```

### Registration

Register by passing the callable to `create_app(health_checks=[...])` in `src/blitz/main.py` or wherever the app is instantiated.

### After implementation
1. Write a test that mocks the dependency to verify both the healthy (`200`) and unhealthy (`503`) paths
2. Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
