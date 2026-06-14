"""Structured JSON access logging.

One JSON line per HTTP request on stdout, so `docker compose logs gateway`
yields machine-parseable records out of the box. This complements — it does not
replace — the two durable controls already in place: OpenTelemetry spans around
every pipeline stage, and the append-only audit trail written for every tool
decision. This log is operational breadcrumbs (method, path, status, latency,
trace id); the audit trail remains the system of record.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from telemetry import current_trace_id

_logger = logging.getLogger("nervora.access")


def configure_json_logging() -> None:
    """Emit one JSON object per log record to stdout. Idempotent."""
    if getattr(configure_json_logging, "_done", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    configure_json_logging._done = True  # type: ignore[attr-defined]


class JSONAccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        record = {
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "trace_id": response.headers.get("X-Trace-Id") or current_trace_id() or "",
            "request_id": response.headers.get("X-Request-Id") or "",
        }
        _logger.info(json.dumps(record, separators=(",", ":")))
        return response
