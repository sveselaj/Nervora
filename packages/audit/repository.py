"""The only sanctioned writer for audit + execution records.

Centralising writes here is a control, not just convenience: it is what makes
"agents cannot suppress audit logging" enforceable. The gateway records a
``tool_calls`` row and an ``audit_events`` row for every decision — including
denials and failures.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from audit.models import (
    Approval,
    AsyncJob,
    AuditEvent,
    IdempotencyKey,
    ToolCall,
    ToolPolicy,
)


class IdempotencyConflict(Exception):
    """Raised when an idempotency key was already reserved/completed."""


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    # --- audit + tool_calls ---------------------------------------------
    def record_event(self, *, trace_id: str, request_id: str, event_type: str,
                     decision: str = "", tool_name: str = "", user_id: str = "",
                     agent_id: str = "", role: str = "", detail: dict | None = None) -> AuditEvent:
        ev = AuditEvent(
            trace_id=trace_id, request_id=request_id, event_type=event_type,
            decision=decision, tool_name=tool_name, user_id=user_id,
            agent_id=agent_id, role=role, detail=detail or {},
        )
        self.s.add(ev)
        return ev

    def record_tool_call(self, **fields: Any) -> ToolCall:
        call = ToolCall(**fields)
        self.s.add(call)
        return call

    # --- tool policy snapshot -------------------------------------------
    def upsert_policy(self, *, tool_name: str, description: str, required_roles: list[str],
                      classification: str, execution_mode: str, pii_classification: str,
                      dry_run_required: bool, enabled: bool) -> None:
        row = self.s.get(ToolPolicy, tool_name)
        if row is None:
            row = ToolPolicy(tool_name=tool_name)
            self.s.add(row)
        row.description = description
        row.required_roles = required_roles
        row.classification = classification
        row.execution_mode = execution_mode
        row.pii_classification = pii_classification
        row.dry_run_required = dry_run_required
        row.enabled = enabled
        row.updated_at = dt.datetime.now(dt.UTC)

    # --- async jobs ------------------------------------------------------
    def create_job(self, **fields: Any) -> AsyncJob:
        job = AsyncJob(**fields)
        self.s.add(job)
        return job

    def get_job(self, job_id: str) -> AsyncJob | None:
        return self.s.get(AsyncJob, job_id)

    def set_job_status(self, job_id: str, status: str, *, result: dict | None = None,
                       error_code: str | None = None, error_detail: str | None = None,
                       attempts: int | None = None) -> AsyncJob | None:
        job = self.s.get(AsyncJob, job_id)
        if job is None:
            return None
        job.status = status
        if result is not None:
            job.result = result
        if error_code is not None:
            job.error_code = error_code
        if error_detail is not None:
            job.error_detail = error_detail
        if attempts is not None:
            job.attempts = attempts
        return job

    # --- idempotency -----------------------------------------------------
    def reserve_idempotency(self, *, idempotency_key: str, tool_name: str,
                            input_hash: str, job_id: str | None = None) -> IdempotencyKey:
        """Reserve a key. Raises :class:`IdempotencyConflict` if it exists."""
        existing = self.s.get(IdempotencyKey, idempotency_key)
        if existing is not None:
            raise IdempotencyConflict(idempotency_key)
        row = IdempotencyKey(
            idempotency_key=idempotency_key, tool_name=tool_name,
            input_hash=input_hash, job_id=job_id, status="reserved",
        )
        self.s.add(row)
        return row

    def get_idempotency(self, idempotency_key: str) -> IdempotencyKey | None:
        return self.s.get(IdempotencyKey, idempotency_key)

    def complete_idempotency(self, idempotency_key: str, result: dict) -> None:
        row = self.s.get(IdempotencyKey, idempotency_key)
        if row is not None:
            row.status = "completed"
            row.result = result

    # --- approvals -------------------------------------------------------
    def create_approval(self, **fields: Any) -> Approval:
        approval = Approval(**fields)
        self.s.add(approval)
        return approval

    def get_approval(self, approval_id: str) -> Approval | None:
        return self.s.get(Approval, approval_id)

    # --- queries (used by admin/status endpoints) ------------------------
    def recent_tool_calls(self, limit: int = 50) -> list[ToolCall]:
        stmt = select(ToolCall).order_by(ToolCall.id.desc()).limit(limit)
        return list(self.s.scalars(stmt))

    def recent_events(self, limit: int = 50) -> list[AuditEvent]:
        stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
        return list(self.s.scalars(stmt))
