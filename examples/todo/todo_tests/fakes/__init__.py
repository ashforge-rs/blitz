"""Test doubles for every port, one module each.

Every fake subclasses its port (an ABC), so a missing method fails on instantiation, and
``integration/test_unit_of_work_contract.py`` runs the same behavioural tests
against the fakes and the SQLite adapters, so a fake can't drift in shape or
in behaviour.
"""

from .clock import EPOCH, FixedClock
from .ids import SequentialIds
from .in_memory_todos_unit_of_work import InMemoryTodosUnitOfWorkFactory
from .in_memory_users_unit_of_work import InMemoryUsersUnitOfWorkFactory
from .recording_audit_backend import RecordingAuditBackend
from .telemetry_recorders import TodoTelemetryRecorder, UserTelemetryRecorder

__all__ = [
    "EPOCH",
    "FixedClock",
    "InMemoryTodosUnitOfWorkFactory",
    "InMemoryUsersUnitOfWorkFactory",
    "RecordingAuditBackend",
    "SequentialIds",
    "TodoTelemetryRecorder",
    "UserTelemetryRecorder",
]
