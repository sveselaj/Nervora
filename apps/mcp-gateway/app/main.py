"""Nervora — Secure MCP Gateway · FastAPI application.

Boots the governed execution stack and exposes:

* ``GET  /healthz`` / ``/health``         liveness
* ``GET  /health/ai``                     AI readiness: services + tool surface
* ``GET  /tools``                         the published tool registry (policies)
* ``POST /tools/{tool_name}/invoke``      the governed execution entrypoint
* ``GET  /jobs/{job_id}``                 async job status
* ``POST /approvals/{approval_id}/approve`` human approval (admin role)
* ``GET  /audit/tool-calls`` / ``/audit/events``  audit trail
* ``GET  /queue/stats``                   local queue depth / DLQ count
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import partial

# Import side-effect: registers the queue_messages table on the shared metadata
# so create_all provisions it alongside the audit tables.
import servicebus.local  # noqa: F401
from audit import AuditRepository, create_all, session_scope
from auth import Principal, build_verifier
from common.settings import get_settings
from databricks_connector import build_connector
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from rbac.roles import AgentRole
from servicebus import build_queue
from telemetry import setup_telemetry
from tool_registry import build_default_registry

from app.deps import get_principal
from app.executor import Executor
from app.logging_mw import JSONAccessLogMiddleware, configure_json_logging
from app.schemas import (
    InvokeRequest,
    InvokeResponse,
    JobView,
    RedactionInfo,
    ToolPolicyView,
)


def _sync_policies(settings, registry) -> None:
    with session_scope(settings.database_url) as session:
        repo = AuditRepository(session)
        for spec in registry.list():
            p = spec.policy_dict()
            repo.upsert_policy(
                tool_name=p["name"], description=p["description"],
                required_roles=p["required_roles"], classification=p["classification"],
                execution_mode=p["execution_mode"], pii_classification=p["pii_classification"],
                dry_run_required=p["dry_run_required"], enabled=p["enabled"],
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_json_logging()
    setup_telemetry(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        enabled=settings.otel_enabled,
        console_fallback=settings.otel_console_fallback,
    )
    create_all(settings.database_url)

    registry = build_default_registry(demo_mode=settings.is_demo)
    _sync_policies(settings, registry)

    queue = build_queue(settings)
    databricks = build_connector(settings)

    app.state.settings = settings
    app.state.registry = registry
    app.state.verifier = build_verifier(settings)
    app.state.queue = queue
    app.state.executor = Executor(
        registry=registry, settings=settings, queue=queue, databricks=databricks,
        session_factory=partial(session_scope, settings.database_url),
    )

    # Instrument FastAPI + SQLAlchemy if the OTel instrumentations are present.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass

    yield


app = FastAPI(
    title="Nervora — Secure MCP Gateway",
    description="Nervora · Secure MCP Gateway for Enterprise AI Tool Execution. "
                "Internal R&D Reference Architecture (mock-first, synthetic data).",
    version="0.1.0",
    lifespan=lifespan,
)

# Structured JSON access log (one line per request) — operational breadcrumbs
# alongside the OTel spans and the durable audit trail.
app.add_middleware(JSONAccessLogMiddleware)

# Demo-only: permissive CORS so the static admin-web page can call the API.
# In production the console is served same-origin / behind an auth proxy.
if get_settings().is_demo:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
        allow_headers=["*"], expose_headers=["X-Trace-Id", "X-Request-Id"],
    )


def _liveness() -> dict:
    s = get_settings()
    return {"status": "ok", "env": s.app_env, "auth_mode": s.auth_mode,
            "queue_backend": s.queue_backend, "databricks_mode": s.databricks_mode}


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    """Liveness probe (legacy path, kept for existing orchestration)."""
    return _liveness()


@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness probe — is the gateway process up and configured?"""
    return _liveness()


@app.get("/health/ai", tags=["ops"])
def health_ai() -> dict:
    """AI-specific readiness: backing services + the published tool surface.

    Shows, deterministically, which tools are registered, which are enabled, and
    which require human approval — the per-tool view the demo flow ends on. No
    secrets are exposed; this is the same policy metadata as ``GET /tools``.
    """
    s = get_settings()
    registry = app.state.registry
    tools = [
        {
            "name": spec.name,
            "classification": spec.classification.value,
            "execution_mode": spec.execution_mode.value,
            "enabled": spec.enabled,
            "requires_approval": spec.dry_run_required or spec.requires_approval_token,
            "required_roles": list(spec.required_roles),
        }
        for spec in registry.list()
    ]
    enabled = sum(1 for t in tools if t["enabled"])
    return {
        "status": "ok",
        "env": s.app_env,
        "services": {
            "auth_mode": s.auth_mode,
            "queue_backend": s.queue_backend,
            "databricks_mode": s.databricks_mode,
            "otel_enabled": s.otel_enabled,
        },
        "tools": {
            "total": len(tools),
            "enabled": enabled,
            "disabled": len(tools) - enabled,
            "registry": tools,
        },
    }


@app.get("/tools", response_model=list[ToolPolicyView], tags=["tools"])
def list_tools() -> list[ToolPolicyView]:
    registry = app.state.registry
    return [ToolPolicyView(**spec.policy_dict()) for spec in registry.list()]


@app.post("/tools/{tool_name}/invoke", response_model=InvokeResponse, tags=["tools"])
def invoke_tool(
    tool_name: str,
    body: InvokeRequest,
    response: Response,
    principal: Principal = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    approval_token: str | None = Header(default=None, alias="X-Approval-Token"),
) -> InvokeResponse:
    executor: Executor = app.state.executor
    outcome = executor.invoke(
        principal=principal,
        tool_name=tool_name,
        arguments=body.arguments,
        idempotency_key=idempotency_key or body.idempotency_key,
        approval_token=approval_token,
    )
    response.status_code = outcome.http_status
    response.headers["X-Trace-Id"] = outcome.trace_id
    response.headers["X-Request-Id"] = outcome.request_id
    return InvokeResponse(
        request_id=outcome.request_id, trace_id=outcome.trace_id, tool=outcome.tool,
        decision=outcome.decision, result=outcome.result, job_id=outcome.job_id,
        approval_id=outcome.approval_id, error_code=outcome.error_code,
        message=outcome.message, latency_ms=outcome.latency_ms,
        redaction=RedactionInfo(
            status=outcome.redaction_status,
            redacted_fields=outcome.redacted_fields or [],
            matched_patterns=outcome.matched_patterns or [],
        ),
    )


@app.get("/jobs/{job_id}", response_model=JobView, tags=["jobs"])
def get_job(job_id: str, principal: Principal = Depends(get_principal)) -> JobView:
    settings = get_settings()
    with session_scope(settings.database_url) as session:
        job = AuditRepository(session).get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobView(
            job_id=job.job_id, tool_name=job.tool_name, status=job.status,
            attempts=job.attempts, result=job.result, error_code=job.error_code,
            trace_id=job.trace_id,
        )


@app.post("/approvals/{approval_id}/approve", tags=["approvals"])
def approve(approval_id: str, principal: Principal = Depends(get_principal)) -> dict:
    """Human-in-the-loop approval. Restricted to the Admin Agent role.

    This is the out-of-band step that a destructive ``execute_crm_update`` call
    later references via its approval token. Note: in demo mode the destructive
    tool stays hard-disabled even after approval.
    """
    if principal.role != AgentRole.ADMIN_AGENT:
        raise HTTPException(status_code=403, detail="only the admin_agent role may approve")
    settings = get_settings()
    with session_scope(settings.database_url) as session:
        repo = AuditRepository(session)
        approval = repo.get_approval(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        approval.status = "approved"
        approval.approved_by = principal.subject
        repo.record_event(
            trace_id="", request_id="", event_type="approval.approved",
            decision="approved", tool_name=approval.tool_name,
            user_id=principal.subject, agent_id=principal.agent_id, role=principal.role,
            detail={"approval_id": approval_id},
        )
        return {"approval_id": approval_id, "status": "approved",
                "approved_by": principal.subject}


@app.get("/audit/tool-calls", tags=["audit"])
def audit_tool_calls(limit: int = 50, principal: Principal = Depends(get_principal)) -> JSONResponse:
    settings = get_settings()
    with session_scope(settings.database_url) as session:
        rows = AuditRepository(session).recent_tool_calls(limit=limit)
        return JSONResponse([
            {"request_id": r.request_id, "trace_id": r.trace_id, "tool_name": r.tool_name,
             "role": r.role, "agent_id": r.agent_id, "decision": r.decision,
             "redaction_status": r.redaction_status, "error_code": r.error_code,
             "latency_ms": r.latency_ms, "created_at": r.created_at.isoformat()}
            for r in rows
        ])


@app.get("/audit/events", tags=["audit"])
def audit_events(limit: int = 50, principal: Principal = Depends(get_principal)) -> JSONResponse:
    settings = get_settings()
    with session_scope(settings.database_url) as session:
        rows = AuditRepository(session).recent_events(limit=limit)
        return JSONResponse([
            {"event_type": r.event_type, "trace_id": r.trace_id, "tool_name": r.tool_name,
             "role": r.role, "decision": r.decision, "detail": r.detail,
             "created_at": r.created_at.isoformat()}
            for r in rows
        ])


@app.get("/queue/stats", tags=["ops"])
def queue_stats(principal: Principal = Depends(get_principal)) -> dict:
    queue = app.state.queue
    if hasattr(queue, "stats"):
        return {"backend": "local", "queue": get_settings().servicebus_queue_name,
                "depth_by_status": queue.stats()}
    return {"backend": "azure", "note": "inspect depth/DLQ in the Azure portal or via Monitor"}
