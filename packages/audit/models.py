"""ORM models for the audit + execution schema.

Six tables, mirroring ``audit/schema.sql``:

* audit_events     — append-only event stream (decisions, lifecycle, errors)
* tool_calls       — one row per gateway tool invocation
* tool_policies    — declarative tool metadata snapshot (name, role, class…)
* async_jobs       — long-running job records
* approvals        — human-approval records for destructive actions
* idempotency_keys — duplicate-execution guard
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from audit.db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="")
    agent_id: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(64), default="")
    tool_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    decision: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="")
    agent_id: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(64), default="")
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    redaction_status: Mapped[str] = mapped_column(String(32), default="none")
    # decision: allowed | denied | dry_run | queued | executed | failed
    decision: Mapped[str] = mapped_column(String(32), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ToolPolicy(Base):
    """A persisted snapshot of each tool's declared policy metadata.

    The tool registry is the source of truth at runtime; this table makes the
    policy queryable/auditable and is refreshed on startup.
    """

    __tablename__ = "tool_policies"

    tool_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")
    required_roles: Mapped[list] = mapped_column(JSON, default=list)
    classification: Mapped[str] = mapped_column(String(32))  # read|write|destructive
    execution_mode: Mapped[str] = mapped_column(String(16))  # sync|async
    pii_classification: Mapped[str] = mapped_column(String(32))  # none|low|sensitive
    dry_run_required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AsyncJob(Base):
    __tablename__ = "async_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(96), index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="")
    agent_id: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # status: queued | running | succeeded | failed | dead_letter
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Approval(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    resource_id: Mapped[str] = mapped_column(String(128))
    proposed_change: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by_agent: Mapped[str] = mapped_column(String(128), default="")
    requested_by_role: Mapped[str] = mapped_column(String(64), default="")
    # status: pending | approved | rejected | consumed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    idempotency_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    # status: reserved | completed
    status: Mapped[str] = mapped_column(String(32), default="reserved")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
