"""After-commit side effects of the HTTP adapter: metrics and blitz audit events.

Best effort by design.  The consent ledger, written in the same transaction as
the decision, *is* the record that proves consent; these are copies for
operations, so a failing audit sink is logged and never fails or undoes a request.
"""

from audit.backend import AuditBackend, AuditIntegrity
from audit.helpers import log_operation
from context import RequestContext
from loguru import logger
from metrics import counter

DECISIONS = counter(
    "consentapp_decisions_total",
    "Consent decisions recorded, by decision, purpose and profile",
    ["decision", "purpose", "profile"],
)
REFUSALS = counter("consentapp_refusals_total", "Requests the use cases refused, by code", ["code"])


async def audit_best_effort(
    backend: AuditBackend,
    integrity: AuditIntegrity,
    ctx: RequestContext,
    operation: str,
    resource_id: str,
) -> None:
    try:
        await log_operation(backend, integrity, ctx, operation, resource_id=resource_id)
    except Exception as exc:  # noqa: BLE001 — the ledger already holds the proof
        logger.warning("consent.audit_copy_failed", operation=operation, error=str(exc))
