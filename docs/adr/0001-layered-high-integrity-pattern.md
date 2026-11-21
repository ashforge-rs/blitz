# 1. Flat domains by default; the layered pattern for high-integrity services

- **Status:** accepted
- **Date:** 2026-11-21

## Context

blitz scaffolds *flat* domains (`make domain`): `models.py`, `errors.py`, `repository.py`,
`service.py`, `dependencies.py`, `domain.py`. They are fast to write and to read, and right for
most services: CRUD plus a few business rules.

`examples/todo/` shows a *layered* (Clean Architecture / ports-and-adapters) alternative:
- entities, ports (abstract base classes), use cases and adapters, per bounded context;
- a unit of work per use case, a transactional audit outbox and idempotency keys;
- fitness tests that enforce the dependency rule;
- two drivers (HTTP and CLI) over the same core.

It buys guarantees, but costs roughly three times the code per use case and more onboarding.
Two undeclared standards in one template make every team, and every coding agent, choose
inconsistently.

## Decision

1. **The flat domain stays the default.** `make domain` and the AGENTS.md domain table describe it.
2. **The layered pattern is the documented choice for high-integrity services.** Choose it when
   at least one of these holds:
   - losing or half-applying a write is unacceptable (money, entitlements, inventory);
   - every state change needs a complete, tamper-evident audit trail (compliance);
   - clients retry over unreliable networks, so writes must be idempotent;
   - the same rules are driven by more than one interface (HTTP, CLI, workers, consumers);
   - the storage technology is expected to change.
3. **A service uses one pattern throughout.** Mixing flat and layered domains in one service is
   not allowed.
4. **`examples/todo/` is the reference** for the layered pattern. Its fitness tests
   (`examples/todo/todo_tests/architecture/`) are copied along with it.

## Consequences

- New services start flat. Moving to layered is a recorded decision (a new ADR), not drift.
- The layered example is maintained to production standards, with versioned migrations and
  Postgres, because people will copy it.
- A future `make domain LAYOUT=layered` may scaffold the layered shape. Until then, copy the
  example.

## Alternatives considered

- **Make layered the default.** Rejected: too much overhead for CRUD-heavy services.
- **Delete the example.** Rejected: the guarantees (atomic audit, idempotency, outage vs bug)
  are hard to get right, and a tested reference is the cheapest way to spread them.
