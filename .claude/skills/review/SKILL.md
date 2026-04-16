---
name: review
description: >
  Deep code review for blitz. Covers correctness, security, architecture,
  type safety, test quality, and CI health. Produces a structured report with
  severity-rated findings and a prioritised fix list. Use when reviewing a PR,
  a new domain, a changed module, or the whole codebase.
license: MIT
metadata:
  author: blitz
  version: "1.0"
---

Perform a thorough, evidence-based code review of the target scope.

**Input**: Optionally a file path, domain name, or PR diff. If omitted, review
the full repository.

---

## Step 0 — Gather scope

Determine what to review:
- If a specific file or domain was named, read it and its tests.
- If reviewing a PR / recent changes, use `git diff main...HEAD` or
  `git diff --name-only HEAD~1` to identify changed files, then read each.
- If no scope given, read all files under `src/` and `tests/`.

Always read `src/config.py`, `src/app.py`, `src/lifespan.py`, and
`src/middleware/stack.py` — they are the wiring layer and bugs here affect
everything.

---

## Step 1 — Run the quality gates

Execute all three checks and capture full output:

```bash
uv run ruff format --check src/ tests/
uv run ruff check src/ tests/
uv run mypy src/ tests/
uv run pytest --tb=short -q
```

Report exact error counts at the top of your findings table. A passing gate is
a prerequisite — if any gate fails, those findings are **CRITICAL** regardless
of other assessment.

---

## Step 2 — Architecture review

For each domain under `src/domains/` (skip `src/domains/example/` unless it is the target):

### 2a. Layer separation (SOLID)

| Layer | File | Must contain | Must NOT contain |
|---|---|---|---|
| Models | `models.py` | Pydantic fields + validators | Business logic, DB calls, imports from service/repo |
| Repository | `repository.py` | Async store calls only | Business rules, HTTP context, `InMemoryStore` import |
| Service | `service.py` | Business rules, `ctx: RequestContext` as last arg | Direct store access, HTTP objects, hardcoded IDs |
| Domain | `domain.py` | `make_router()`, `bootstrap()`, route handlers | Business logic (must delegate to service) |
| Dependencies | `dependencies.py` | `Depends` factories only | Logic beyond extracting from `request.app.state` |

Flag any violation as **ARCHITECTURE** severity.

### 2b. bootstrap() wiring

`bootstrap(settings, **kwargs)` must follow exactly:
```
InMemoryStore[K, V] → {X}Repository(store=...) → {X}Service(repository=...) → {X}Domain(service=...)
```

- `InMemoryStore` must only appear in `bootstrap()`, never in repo/service constructors.
- The domain instance must be stored at `app.state.domains[module.__name__]` (handled by `lifespan.py`).
- `make_router()` must return the module-level `_router`, not create a new one per call.

### 2c. RequestContext flow

Every `async def` method on `{X}Service` must:
- Accept `ctx: RequestContext` as its last positional parameter.
- Use `ctx.set(key, value)` to record provenance for at least create/update operations.
- Never import `Request` or access HTTP objects — `ctx` is a plain dataclass.

### 2d. Dependency injection

`dependencies.py` must:
- Resolve the domain via `request.app.state.domains["{module}"]` — not a global.
- Expose typed aliases (`{X}ServiceDep`, `RequestContextDep`) using `Annotated[..., Depends(...)]`.
- Never instantiate services or stores directly.

---

## Step 3 — Security review

Work through each item. Any **YES** triggers a finding.

### Authentication & authorisation
- [ ] Routes that should be protected are missing `Depends(get_auth_context)`?
- [ ] `AuthProvider.authenticate()` can return `None` without triggering 401?
- [ ] `AuthProvider.authorize()` can return `False` without triggering 403?
- [ ] JWT verification skips expiry, signature, or audience checks?
- [ ] Secrets (`DATABASE_URL`, API keys, JWT secret) stored as plain `str` instead of `SecretStr`?

### Input validation
- [ ] Route parameters accepted without Pydantic validation?
- [ ] Pydantic models missing field length / format constraints?
- [ ] File uploads accepted without size or MIME type checks?
  (`python-multipart` is installed; ensure `UploadFile` constraints are applied)
- [ ] Query parameters used in store keys without sanitisation?

### Headers & transport
- [ ] `SecurityHeadersMiddleware` bypassed or removed?
- [ ] `Content-Security-Policy` weakened beyond the dev-only allowlist?
- [ ] `HSTS` sent in non-production environments?
  (Check `middleware/security.py`: HSTS must be in `_PROD_ONLY_HEADERS`)
- [ ] `CORS_ALLOW_CREDENTIALS=true` combined with `ALLOWED_ORIGINS=*`?
  (The pydantic validator in `Settings` must catch this at startup)

### Rate limiting & DoS
- [ ] Rate limiter exempt paths include non-probe endpoints?
- [ ] `MemoryStorage` used in a multi-worker deployment?
  (Note: warn if `WORKERS > 1` and no custom `rate_limit_storage` is provided)
- [ ] Body size limit removed or set to an unreasonably large value?
- [ ] Request timeout removed or set to > 60 seconds?

### Audit trail
- [ ] `NoopAuditBackend` used in production?
- [ ] `audit_integrity` left as `NoIntegrity` for compliance-sensitive deployments?
- [ ] Audit events missing `principal` (authentication not wired)?

### Error handling
- [ ] Unhandled exceptions leak stack traces or internal state in production?
  (Check `ENVIRONMENT=production` triggers the sanitised 500 path in `errors/handlers.py`)
- [ ] `AppError.message` contains raw database errors or file paths?

### Dependency supply chain
- [ ] `uv.lock` not committed?
- [ ] Dependencies pinned with `>=` only (no upper bound is fine; no pin at all is not)?

---

## Step 4 — Type safety review

Run `uv run mypy src/ tests/` if not already done.

Beyond zero errors, inspect manually:

- [ ] `Any` used to silence a real type error (not a necessary escape hatch)?
- [ ] `# type: ignore` without an explanatory comment?
- [ ] Missing return type on any public function in `src/`?
- [ ] `cast()` used to paper over an architectural type mismatch?
- [ ] `Optional[X]` instead of `X | None` (PEP 604 style required)?
- [ ] `from __future__ import annotations` missing from any `.py` file?

---

## Step 5 — Test quality review

### Coverage
- Minimum 80% total (enforced by `--cov-fail-under=80` in CI).
- Any domain at < 90% is a **WARNING**.
- Any domain at < 70% is a **CRITICAL** — flag every uncovered branch.

### Three-layer completeness
For each domain, all three test layers must exist:

| Layer | Required assertions |
|---|---|
| Unit (`tests/domains/<name>/unit/` + `tests/global/unit/`) | Each service method called with valid + invalid inputs; ctx.set() calls verified |
| Integration (`tests/domains/<name>/integration/` + `tests/global/integration/`) | All HTTP routes: success path, 404, 422, auth-gated paths |
| Fuzz (`tests/domains/<name>/fuzz/`) | At least one `@given` test per model; service invariants verified |

### Test correctness
- [ ] `AsyncClient` used without `LifespanManager`?
  (Domain bootstrap never runs → `KeyError` at runtime, not caught by tests)
- [ ] Tests assert on response status code only, not response body?
- [ ] Mocks replace real business logic instead of infrastructure?
- [ ] `@pytest.mark.skip` or `xfail` with no issue reference?
- [ ] Hypothesis `@settings(max_examples=1)` or other suppressed fuzz depth?
- [ ] `dirty-equals` available but plain string comparisons used for IDs/dates?

### Fixtures
- [ ] `test_settings` fixture overrides `ENVIRONMENT="test"` and a high `RATE_LIMIT`?
- [ ] `app` fixture registers all domains under test?
- [ ] `client` fixture yields inside both `LifespanManager` and `AsyncClient` context managers?

---

## Step 6 — CI review

Read `.github/workflows/ci.yml`.

- [ ] Ruff format check present (`ruff format --check`)?
- [ ] Ruff lint present (`ruff check`)?
- [ ] mypy step present? If absent, flag as **WARNING** — type errors accumulate silently.
- [ ] Tests run against multiple Python versions (matrix)?
- [ ] `--cov-fail-under=80` enforced in test command?
- [ ] `uv sync --frozen` used (not `uv sync` — reproducible builds)?
- [ ] Concurrency group set to cancel superseded runs?
- [ ] Codecov or equivalent coverage upload present?

---

## Step 7 — Produce the report

Output a structured report in this exact format:

---

### Review Report — `<scope>`

**Quality gates**

| Gate | Status | Details |
|---|---|---|
| `ruff format` | ✅/❌ | N files reformatted / already clean |
| `ruff check` | ✅/❌ | N errors |
| `mypy` | ✅/❌ | N errors in N files |
| `pytest` | ✅/❌ | N passed, N failed, N% coverage |

---

**Findings**

| # | Severity | Category | File | Finding |
|---|---|---|---|---|
| 1 | 🔴 CRITICAL | Security | `src/auth/dependency.py:42` | … |
| 2 | 🟠 HIGH | Architecture | `src/orders/service.py:18` | … |
| 3 | 🟡 WARNING | Tests | `tests/domains/orders/unit/test_service.py` | … |
| 4 | 🔵 INFO | Style | `src/orders/models.py:5` | … |

Severity scale:
- 🔴 **CRITICAL** — security vulnerability, data loss risk, or quality gate failure
- 🟠 **HIGH** — architectural violation, missing test layer, real type error
- 🟡 **WARNING** — suboptimal pattern, coverage gap, missing CI step
- 🔵 **INFO** — style, naming, minor improvement

---

**Prioritised fix list**

List CRITICAL and HIGH findings as numbered action items with the exact change
needed. Include the file path and line number where applicable. Be specific
enough that a developer can action each item without further clarification.

Do NOT list INFO items in the fix list — mention them in the findings table only.

---

**Summary**

One paragraph: overall health, top risk, and recommended first action.

---

## What NOT to do

- Do not award a pass if a quality gate fails — gates are binary.
- Do not suggest adding docstrings, comments, or annotations to code you are not flagging as broken.
- Do not flag `example` domain issues as bugs — it is the reference implementation and is intentionally complete.
- Do not hallucinate file contents — only report findings backed by lines you actually read.
- Do not produce a "nice job" summary if there are CRITICAL findings — be direct.
