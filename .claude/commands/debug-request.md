Debug a failing or misbehaving request in this blitz application.

Arguments: $ARGUMENTS

## Checklist — work through these in order

### 1. Reproduce with a test
Write or locate the test that surfaces the failure. Run with:
```bash
uv run pytest tests/<file>.py::test_<name> -v --tb=long
```

### 2. Middleware execution order
Requests flow through middleware **outermost → innermost**:
```
InFlight → Audit → SecurityHeaders → Timeout → SizeLimit → RateLimit → Context → Handler
```
- **429** — rate limit tripped. Check `RATE_LIMIT` env var and the client IP key.
- **413** — body exceeded `MAX_REQUEST_SIZE_BYTES` (default 10 MB).
- **504** — handler exceeded `REQUEST_TIMEOUT_SECONDS` (default 30 s).
- **Missing `request.state.ctx`** — `RequestContextMiddleware` didn't run; check that the route is not mounted outside the middleware stack.

### 3. Auth dependency
- **401** — `authenticate()` returned `None`. Add logging inside your `AuthProvider.authenticate()`.
- **403** — `authorize()` returned `False`. Check the principal's scopes/roles.
- **No auth check at all** — confirm the route uses `Depends(get_auth_context)`.

### 4. Error sanitisation
In `production`, all unhandled exceptions return `{"detail": "Internal server error"}`.
Switch to `ENVIRONMENT=development` locally to see `type` + `message` in the response body.
Full tracebacks are always in the Loguru output regardless of environment.

### 5. Audit events
If an `AuditEvent` is missing or has wrong fields:
- Check `AuditMiddleware` — it reads `app.state.audit_backend` at request time.
- `principal` is `None` unless the auth dependency ran and called `ctx.set("principal", ...)`.

### 6. Prometheus metrics
```bash
curl http://localhost:8000/metrics | grep <metric_name>
```
If a metric is missing, confirm the module defining it was imported before the first request.

### 7. Common commands
```bash
make test          # run all tests
make lint          # ruff check
make fmt           # ruff format
uv run pytest -v --tb=short   # concise failures
uv run pytest -v --tb=long    # full tracebacks
```
