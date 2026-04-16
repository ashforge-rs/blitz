---
name: soc2-compliance-eval
description: Evaluate the basics of SOC II compliance for this codebase. Use when the user wants to assess how well the project aligns with SOC 2 Trust Service Criteria, identify gaps, and get actionable guidance.
license: MIT
metadata:
  author: blitz
  version: "1.0"
---

Evaluate the codebase and configuration against the SOC 2 Trust Service Criteria (TSC). Be concrete — point to specific files, settings, and patterns. Highlight gaps clearly and suggest actionable remediations.

---

## SOC 2 Overview

SOC 2 (System and Organization Controls 2) is an auditing standard developed by the AICPA. It evaluates controls relevant to the **Trust Service Criteria (TSC)**:

| Criterion | Code | Description |
|---|---|---|
| Security | CC | Protection against unauthorized access (always required) |
| Availability | A | System is available for operation as committed |
| Processing Integrity | PI | Processing is complete, valid, accurate, timely |
| Confidentiality | C | Designated confidential information is protected |
| Privacy | P | Personal information is collected, used, retained, disclosed appropriately |

**Security (CC) is the only mandatory criterion.** The others are in scope only if the service commits to them.

---

## Evaluation Framework

Work through each category below. For each area:
1. Search the codebase for relevant code/config
2. Assess whether controls are present, partial, or absent
3. Rate as: ✅ Present | ⚠️ Partial | ❌ Missing
4. Provide a concrete finding and remediation suggestion

---

## CC — Security (Common Criteria)

### CC6: Logical and Physical Access Controls

**Authentication & Authorization**
- Is there an `AuthProvider` implementation beyond the default no-op?
- Are routes protected with `get_auth_context` dependencies?
- Are JWTs validated with expiry, signature, and audience checks?
- Are secrets (API keys, DB passwords) loaded from environment variables, not hardcoded?

Look at:
- `src/auth/protocol.py` — AuthProvider protocol
- `src/auth/dependency.py` — route protection dependency
- `src/config.py` — are secrets typed as `SecretStr`?
- `.env.example` — are sensitive defaults avoided?

**Rate Limiting**
- Is `RATE_LIMIT` configured appropriately (not too permissive)?
- Is `MemoryStorage` used (single-process only, not suitable for multi-worker)?
- For multi-worker deployments: is a shared backend (Redis) configured?

Look at: `src/middleware/rate_limit.py`, `src/config.py`

### CC7: System Operations

**Audit Logging**
- Is an `AuditBackend` configured (not `noop`)?
- Do audit events capture: who (principal), what (action), when (timestamp), result (success/failure)?
- Are logs tamper-evident or shipped to an immutable store?
- Is `AuditIntegrity` used for signing/hashing audit events?

Look at:
- `src/audit/backend.py`
- `src/audit/integrity.py`
- `src/audit/backends/`
- `src/middleware/audit.py`

**Error Handling**
- Are internal errors sanitised before reaching clients (no stack traces in production)?
- Is `ENVIRONMENT=production` disabling `/docs` and verbose errors?

Look at: `src/errors/handlers.py`, `src/config.py`

### CC8: Change Management

- Is there a CI/CD pipeline (`.github/workflows/`, `Dockerfile`, etc.)?
- Are dependency versions pinned (`uv.lock` committed)?
- Is there a test suite with meaningful coverage (`tests/`)?

### CC9: Risk Mitigation

**Input Validation**
- Are request bodies validated via Pydantic models (not raw dicts)?
- Is `MAX_REQUEST_SIZE_BYTES` set to a safe value (default 10 MB)?
- Is `REQUEST_TIMEOUT_SECONDS` set to prevent slow-loris attacks?

**Transport Security**
- Are `SecurityHeaders` middleware enabled (HSTS, X-Frame-Options, CSP)?
- Is TLS termination handled upstream (reverse proxy, load balancer)?

Look at: `src/middleware/security.py`, `src/middleware/size_limit.py`, `src/middleware/timeout.py`

---

## A — Availability

- Are liveness (`GET /live`) and readiness (`GET /health`) probes implemented and registered with an orchestrator?
- Are health checks registered for all critical dependencies (DB, cache, external APIs)?
- Is `SHUTDOWN_TIMEOUT_SECONDS` set to allow graceful drain?
- Are there runbooks or alerting rules (check `grafana/alerts.yml`)?

Look at: `src/routes/health.py`, `src/lifespan.py`, `grafana/`

---

## PI — Processing Integrity

- Are all data mutations validated before persistence (Pydantic, DB constraints)?
- Are idempotency keys or transaction IDs used where relevant?
- Is there structured logging of processing outcomes via the audit backend?

---

## C — Confidentiality

- Are secrets stored as `SecretStr` and never logged?
- Are sensitive fields excluded from audit event payloads?
- Is data encrypted at rest (DB-level, storage-level)?
- Are API responses filtered to return only the minimum necessary data?

---

## P — Privacy

- Is PII identified and documented?
- Are retention/deletion policies implemented?
- Are third-party data processors documented?
- Does the app comply with applicable regulations (GDPR, CCPA)?

---

## Quick Checklist Template

Use this to produce a summary table after evaluation:

```
| Area                         | Status | Finding                              | Remediation                      |
|------------------------------|--------|--------------------------------------|----------------------------------|
| AuthProvider implemented     | ❌      | Default no-op used                   | Implement JWT/OAuth provider     |
| Routes protected             | ⚠️      | Only /secret route guarded           | Audit all routes                 |
| Secrets as SecretStr         | ✅      | All secrets use SecretStr            | —                                |
| Audit backend not noop       | ⚠️      | Loguru backend used, no integrity    | Add AuditIntegrity signing       |
| Rate limit storage           | ⚠️      | MemoryStorage (single worker only)   | Use RedisStorage in production   |
| Security headers             | ✅      | SecurityHeadersMiddleware enabled    | —                                |
| Request size limit           | ✅      | MAX_REQUEST_SIZE_BYTES=10485760      | —                                |
| Request timeout              | ✅      | REQUEST_TIMEOUT_SECONDS=30           | —                                |
| Health checks registered     | ⚠️      | No dependency checks registered      | Add DB/cache health checks       |
| Graceful shutdown            | ✅      | SHUTDOWN_TIMEOUT_SECONDS configured  | —                                |
| Dependency pinning           | ✅      | uv.lock committed                    | —                                |
| Error sanitisation           | ✅      | Sanitised 500s in production         | —                                |
```

---

## Output Format

Provide:
1. **Scope** — which TSC criteria are in scope for this system
2. **Summary table** — the checklist above, filled in
3. **Top 3–5 gaps** — prioritised by risk, with concrete file references and remediation steps
4. **Strengths** — what the codebase already does well

Keep findings grounded in the actual code. Reference specific files and line numbers where possible. Avoid generic advice not backed by what was found.
