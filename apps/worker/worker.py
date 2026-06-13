"""The async tool-execution worker.

Receives queued jobs (Service Bus abstraction), and for each message:

1. **Idempotency check** — if the idempotency key is already ``completed``,
   the job has run before (a duplicate delivery); settle the message and skip
   re-execution.
2. **Execute** — mark the job ``running``, increment attempts, run the tool's
   handler.
3. **Settle**:
   * success  -> job ``succeeded``, idempotency key ``completed``,
                 message completed.
   * failure  -> if delivery attempts remain, ``abandon`` the message so the
                 broker redelivers (retry); once the max delivery count is hit
                 the message is dead-lettered and the job marked ``dead_letter``.

Every outcome is written to the audit trail. Run modes:
``poll_once`` (used by tests) and ``run_forever`` (the service entrypoint).
"""

from __future__ import annotations

import signal
import time
from typing import Any

import servicebus.local  # noqa: F401  (registers queue table)
from audit import AuditRepository, create_all, session_scope
from common.settings import Settings, get_settings
from databricks_connector import build_connector
from servicebus import build_queue
from servicebus.interface import Message, MessageQueue
from telemetry import setup_telemetry, span
from tool_registry import ToolContext, ToolError, build_default_registry


class Worker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = build_default_registry(demo_mode=self.settings.is_demo)
        self.queue: MessageQueue = build_queue(self.settings)
        self.tool_ctx = ToolContext(
            settings=self.settings, databricks=build_connector(self.settings)
        )
        self.max_delivery = self.settings.queue_max_delivery_count
        self._running = False

    # ----------------------------------------------------------------------
    def _process(self, message: Message) -> None:
        body = message.body
        job_id = body.get("job_id")
        idk = body.get("idempotency_key")
        tool_name = body.get("tool_name", "")
        arguments: dict[str, Any] = body.get("arguments", {})
        db = self.settings.database_url

        with span("worker.execute", {"tool": tool_name, "job_id": job_id or ""}):
            # 1. idempotency guard ----------------------------------------
            with session_scope(db) as s:
                repo = AuditRepository(s)
                idem = repo.get_idempotency(idk) if idk else None
                if idem is not None and idem.status == "completed":
                    repo.set_job_status(job_id, "succeeded", result=idem.result or {})
                    repo.record_event(
                        trace_id=body.get("trace_id", ""), request_id=job_id or "",
                        event_type="job.duplicate_skipped", decision="executed",
                        tool_name=tool_name, detail={"idempotency_key": idk})
                    self.queue.complete(message)
                    return

            spec = self.registry.get(tool_name)
            if spec is None:
                # Unknown tool in a message — non-retryable; dead-letter it.
                with session_scope(db) as s:
                    repo = AuditRepository(s)
                    repo.set_job_status(job_id, "dead_letter", error_code="UNKNOWN_TOOL",
                                        error_detail=f"tool {tool_name} not registered")
                    repo.record_event(trace_id=body.get("trace_id", ""), request_id=job_id or "",
                                      event_type="job.dead_letter", decision="failed",
                                      tool_name=tool_name, detail={"reason": "unknown_tool"})
                self.queue.dead_letter(message, reason="unknown tool")
                return

            # 2. execute --------------------------------------------------
            with session_scope(db) as s:
                AuditRepository(s).set_job_status(
                    job_id, "running", attempts=message.delivery_count)
            try:
                result = spec.run(self.tool_ctx, arguments)
            except (ToolError, Exception) as exc:  # noqa: BLE001 — classify below
                self._handle_failure(message, body, tool_name, exc)
                return

            # 3. settle success -------------------------------------------
            with session_scope(db) as s:
                repo = AuditRepository(s)
                repo.set_job_status(job_id, "succeeded", result=result.output,
                                    attempts=message.delivery_count)
                if idk:
                    repo.complete_idempotency(idk, result.output)
                repo.record_event(trace_id=body.get("trace_id", ""), request_id=job_id or "",
                                  event_type="job.succeeded", decision="executed",
                                  tool_name=tool_name, detail={"job_id": job_id})
            self.queue.complete(message)

    def _handle_failure(self, message: Message, body: dict, tool_name: str, exc: Exception) -> None:
        job_id = body.get("job_id")
        db = self.settings.database_url
        error_code = getattr(exc, "code", "EXECUTION_ERROR")
        will_dead_letter = message.delivery_count >= self.max_delivery
        status = "dead_letter" if will_dead_letter else "failed"
        with session_scope(db) as s:
            repo = AuditRepository(s)
            repo.set_job_status(job_id, status, error_code=error_code,
                                error_detail=str(exc), attempts=message.delivery_count)
            repo.record_event(
                trace_id=body.get("trace_id", ""), request_id=job_id or "",
                event_type="job.dead_letter" if will_dead_letter else "job.retry",
                decision="failed", tool_name=tool_name,
                detail={"error_code": error_code, "attempt": message.delivery_count,
                        "max_delivery": self.max_delivery})
        # abandon() redelivers, and auto dead-letters once max delivery is hit.
        self.queue.abandon(message)

    # ----------------------------------------------------------------------
    def poll_once(self, *, max_messages: int = 10, visibility_timeout: int = 30) -> int:
        messages = self.queue.receive(
            max_messages=max_messages, visibility_timeout=visibility_timeout)
        for message in messages:
            self._process(message)
        return len(messages)

    def run_forever(self, *, idle_sleep: float = 1.0) -> None:
        self._running = True

        def _stop(*_a):  # graceful shutdown on SIGTERM/SIGINT
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        print(f"[worker] started; backend={self.settings.queue_backend} "
              f"queue={self.settings.servicebus_queue_name} max_delivery={self.max_delivery}")
        while self._running:
            try:
                processed = self.poll_once()
            except Exception as exc:  # never die on a transient error
                print(f"[worker] poll error: {exc}")
                processed = 0
            if processed == 0:
                time.sleep(idle_sleep)
        print("[worker] stopped")


def main() -> None:
    settings = get_settings()
    setup_telemetry(
        service_name="mcp-worker",
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        enabled=settings.otel_enabled,
        console_fallback=settings.otel_console_fallback,
    )
    create_all(settings.database_url)
    Worker(settings).run_forever()


if __name__ == "__main__":
    main()
