"""The governed execution pipeline.

Every tool call flows through :meth:`Executor.invoke`, which enforces the
gateway's guarantees in a fixed order and records the outcome no matter what:

    RBAC  ->  arg validation  ->  destructive/dry-run/async routing  ->
    execute (sync) / enqueue (async)  ->  PII redaction  ->  audit write

The decision recorded is one of: ``allowed`` (internal), ``denied``,
``dry_run``, ``queued``, ``executed``, ``failed``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from audit.repository import AuditRepository, IdempotencyConflict
from common import gen_idempotency_key, gen_request_id, sha256_hex
from common.settings import Settings
from pii import redact
from rbac import all_roles, evaluate
from servicebus.interface import MessageQueue
from telemetry import current_trace_id, span
from tool_registry import ToolContext, ToolError, ToolRegistry, ToolSpec
from tool_registry.spec import Classification, ExecutionMode


@dataclass
class InvocationOutcome:
    request_id: str
    trace_id: str
    tool: str
    decision: str
    result: dict[str, Any] | None = None
    job_id: str | None = None
    approval_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    redaction_status: str = "none"
    redacted_fields: list[str] | None = None
    matched_patterns: list[str] | None = None
    latency_ms: float = 0.0

    @property
    def http_status(self) -> int:
        return {
            "denied": 403,
            "queued": 202,
            "dry_run": 200,
            "executed": 200,
            "failed": 400,
        }.get(self.decision, 200)


class Executor:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        settings: Settings,
        queue: MessageQueue,
        databricks: Any,
        session_factory,
    ) -> None:
        self.registry = registry
        self.settings = settings
        self.queue = queue
        self.tool_ctx = ToolContext(settings=settings, databricks=databricks)
        self._session_factory = session_factory
        self._known_roles = set(all_roles())

    def invoke(
        self,
        *,
        principal,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
        approval_token: str | None = None,
        request_id: str | None = None,
    ) -> InvocationOutcome:
        started = time.perf_counter()
        request_id = request_id or gen_request_id()
        trace_id = current_trace_id() or uuid.uuid4().hex
        input_hash = sha256_hex({"tool": tool_name, "args": arguments})

        spec = self.registry.get(tool_name)

        with self._session_factory() as session:
            repo = AuditRepository(session)

            def finish(outcome: InvocationOutcome) -> InvocationOutcome:
                outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
                repo.record_tool_call(
                    trace_id=trace_id, request_id=request_id,
                    user_id=principal.subject, agent_id=principal.agent_id,
                    role=principal.role, tool_name=tool_name, input_hash=input_hash,
                    redaction_status=outcome.redaction_status, decision=outcome.decision,
                    error_code=outcome.error_code, latency_ms=outcome.latency_ms,
                )
                repo.record_event(
                    trace_id=trace_id, request_id=request_id,
                    event_type=f"tool.{outcome.decision}", decision=outcome.decision,
                    tool_name=tool_name, user_id=principal.subject,
                    agent_id=principal.agent_id, role=principal.role,
                    detail={"error_code": outcome.error_code, "message": outcome.message},
                )
                return outcome

            # --- unknown tool: never silently no-op ----------------------
            if spec is None:
                return finish(InvocationOutcome(
                    request_id=request_id, trace_id=trace_id, tool=tool_name,
                    decision="denied", error_code="UNKNOWN_TOOL",
                    message=f"tool '{tool_name}' is not in the published registry",
                ))

            # --- 1. RBAC -------------------------------------------------
            with span("rbac.decision", {"tool": tool_name, "role": principal.role}):
                decision = evaluate(
                    role=principal.role,
                    required_roles=spec.required_roles,
                    known_roles=self._known_roles,
                    tool_enabled=spec.enabled,
                )
            if not decision.allowed:
                return finish(InvocationOutcome(
                    request_id=request_id, trace_id=trace_id, tool=tool_name,
                    decision="denied", error_code=decision.code, message=decision.detail,
                ))

            # --- 2. validate arguments -----------------------------------
            try:
                args = spec.validate_args(arguments)
            except Exception as exc:
                return finish(InvocationOutcome(
                    request_id=request_id, trace_id=trace_id, tool=tool_name,
                    decision="failed", error_code="INVALID_ARGUMENTS", message=str(exc),
                ))

            # --- 3. route by classification/mode -------------------------
            try:
                if spec.classification is Classification.DESTRUCTIVE:
                    return finish(self._handle_destructive(
                        repo, spec, principal, args, approval_token,
                        request_id, trace_id))
                if spec.dry_run_required:
                    return finish(self._handle_dry_run(
                        repo, spec, principal, args, request_id, trace_id))
                if spec.execution_mode is ExecutionMode.ASYNC:
                    return finish(self._handle_async(
                        repo, spec, principal, args, input_hash,
                        idempotency_key, request_id, trace_id))
                return finish(self._handle_sync(
                    spec, principal, args, request_id, trace_id))
            except ToolError as exc:
                return finish(InvocationOutcome(
                    request_id=request_id, trace_id=trace_id, tool=tool_name,
                    decision="failed", error_code=exc.code, message=str(exc)))
            except Exception as exc:  # defensive: never leak an unhandled error
                return finish(InvocationOutcome(
                    request_id=request_id, trace_id=trace_id, tool=tool_name,
                    decision="failed", error_code="INTERNAL_ERROR", message=str(exc)))

    # ----------------------------------------------------------------------
    def _redact_output(self, spec: ToolSpec, principal, result_output: dict) -> tuple[dict, Any]:
        allow_raw = principal.role in spec.raw_pii_roles
        with span("pii.redaction", {"tool": spec.name, "allow_raw": allow_raw}):
            red = redact(result_output, sensitive_fields=set(spec.sensitive_fields),
                         allow_raw=allow_raw)
        return red.data, red

    def _handle_sync(self, spec, principal, args, request_id, trace_id) -> InvocationOutcome:
        with span("tool.execute", {"tool": spec.name, "mode": "sync"}):
            result = spec.run(self.tool_ctx, args)
        redacted, red = self._redact_output(spec, principal, result.output)
        return InvocationOutcome(
            request_id=request_id, trace_id=trace_id, tool=spec.name,
            decision="executed", result=redacted,
            redaction_status=red.status, redacted_fields=red.redacted_fields,
            matched_patterns=red.matched_patterns,
        )

    def _handle_dry_run(self, repo, spec, principal, args, request_id, trace_id) -> InvocationOutcome:
        with span("tool.execute", {"tool": spec.name, "mode": "dry_run"}):
            result = spec.run(self.tool_ctx, args)  # guaranteed not to write
        approval_id = "apr_" + uuid.uuid4().hex[:16]
        repo.create_approval(
            approval_id=approval_id,
            tool_name=spec.name,
            resource_id=str(result.metadata.get("resource_id", "")),
            proposed_change=result.metadata.get("proposed_change", {}),
            requested_by_agent=principal.agent_id,
            requested_by_role=principal.role,
            status="pending",
        )
        redacted, red = self._redact_output(spec, principal, result.output)
        redacted["approval_id"] = approval_id
        return InvocationOutcome(
            request_id=request_id, trace_id=trace_id, tool=spec.name,
            decision="dry_run", result=redacted, approval_id=approval_id,
            redaction_status=red.status, redacted_fields=red.redacted_fields,
            matched_patterns=red.matched_patterns,
            message="Dry run only — no writes performed. Human approval required.",
        )

    def _handle_async(self, repo, spec, principal, args, input_hash,
                      idempotency_key, request_id, trace_id) -> InvocationOutcome:
        # Idempotency key is mandatory for async/non-idempotent actions; the
        # gateway generates one if the client did not supply it.
        idk = idempotency_key or gen_idempotency_key()

        existing = repo.get_idempotency(idk)
        if existing is not None:
            # Duplicate submission — return the original job, do not re-enqueue.
            return InvocationOutcome(
                request_id=request_id, trace_id=trace_id, tool=spec.name,
                decision="queued", job_id=existing.job_id,
                message="duplicate idempotency key — returning existing job",
            )

        job_id = "job_" + uuid.uuid4().hex[:16]
        try:
            repo.reserve_idempotency(
                idempotency_key=idk, tool_name=spec.name,
                input_hash=input_hash, job_id=job_id)
        except IdempotencyConflict:
            existing = repo.get_idempotency(idk)
            return InvocationOutcome(
                request_id=request_id, trace_id=trace_id, tool=spec.name,
                decision="queued", job_id=existing.job_id if existing else None,
                message="duplicate idempotency key — returning existing job",
            )

        repo.create_job(
            job_id=job_id, trace_id=trace_id, request_id=request_id,
            tool_name=spec.name, idempotency_key=idk,
            user_id=principal.subject, agent_id=principal.agent_id,
            role=principal.role, payload={"arguments": args}, status="queued",
        )
        with span("queue.publish", {"tool": spec.name, "job_id": job_id}):
            self.queue.publish({
                "job_id": job_id,
                "idempotency_key": idk,
                "tool_name": spec.name,
                "trace_id": trace_id,
                "arguments": args,
            })
        return InvocationOutcome(
            request_id=request_id, trace_id=trace_id, tool=spec.name,
            decision="queued", job_id=job_id,
            message="job queued for asynchronous execution",
        )

    def _handle_destructive(self, repo, spec, principal, args, approval_token,
                            request_id, trace_id) -> InvocationOutcome:
        # Destructive tools are deny-by-default. The gate is, in order:
        #   tool enabled  ->  valid approval token  ->  approval record approved
        if not spec.enabled:
            return InvocationOutcome(
                request_id=request_id, trace_id=trace_id, tool=spec.name,
                decision="denied", error_code="tool_disabled",
                message="destructive tool is disabled in this environment (demo mode)")

        configured = self.settings.admin_approval_token
        if not configured or not approval_token or approval_token != configured:
            return InvocationOutcome(
                request_id=request_id, trace_id=trace_id, tool=spec.name,
                decision="denied", error_code="APPROVAL_REQUIRED",
                message="a valid X-Approval-Token is required for destructive execution")

        approval_id = args.get("approved_change_id")
        approval = repo.get_approval(approval_id) if approval_id else None
        if approval is None or approval.status != "approved":
            return InvocationOutcome(
                request_id=request_id, trace_id=trace_id, tool=spec.name,
                decision="denied", error_code="APPROVAL_NOT_APPROVED",
                message="referenced approval does not exist or is not in 'approved' state")

        with span("tool.execute", {"tool": spec.name, "mode": "destructive"}):
            result = spec.run(self.tool_ctx, args)
        approval.status = "consumed"
        approval.approved_by = principal.subject
        redacted, red = self._redact_output(spec, principal, result.output)
        return InvocationOutcome(
            request_id=request_id, trace_id=trace_id, tool=spec.name,
            decision="executed", result=redacted, approval_id=approval_id,
            redaction_status=red.status)
