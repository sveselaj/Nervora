"""Request/response models for the gateway HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Optional client-supplied idempotency key for async/destructive tools.
    idempotency_key: str | None = None


class RedactionInfo(BaseModel):
    status: str = "none"
    redacted_fields: list[str] = Field(default_factory=list)
    matched_patterns: list[str] = Field(default_factory=list)


class InvokeResponse(BaseModel):
    request_id: str
    trace_id: str
    tool: str
    decision: str  # allowed|denied|dry_run|queued|executed|failed
    result: dict[str, Any] | None = None
    job_id: str | None = None
    approval_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    redaction: RedactionInfo = Field(default_factory=RedactionInfo)
    latency_ms: float = 0.0


class ToolPolicyView(BaseModel):
    name: str
    description: str
    required_roles: list[str]
    classification: str
    execution_mode: str
    pii_classification: str
    dry_run_required: bool
    enabled: bool
    requires_approval_token: bool


class JobView(BaseModel):
    job_id: str
    tool_name: str
    status: str
    attempts: int
    result: dict[str, Any] | None = None
    error_code: str | None = None
    trace_id: str
