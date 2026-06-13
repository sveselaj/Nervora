"""Audit + persistence layer.

Owns the database schema for the whole system: audit_events, tool_calls,
tool_policies, async_jobs, approvals and idempotency_keys. The
:class:`AuditRepository` is the only sanctioned way to write audit records,
which keeps the "agents cannot suppress audit logging" guarantee enforceable
in one place.
"""

from audit.db import Base, create_all, get_engine, get_sessionmaker, session_scope
from audit.models import (
    Approval,
    AsyncJob,
    AuditEvent,
    IdempotencyKey,
    ToolCall,
    ToolPolicy,
)
from audit.repository import AuditRepository

__all__ = [
    "Base",
    "create_all",
    "session_scope",
    "get_engine",
    "get_sessionmaker",
    "AuditEvent",
    "ToolCall",
    "ToolPolicy",
    "AsyncJob",
    "Approval",
    "IdempotencyKey",
    "AuditRepository",
]
