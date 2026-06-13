"""OpenTelemetry setup + a thin span helper used across services.

``setup_telemetry`` configures a tracer provider that exports OTLP to a
collector when one is configured, and falls back to console export for local
runs. ``span`` is a convenience context manager that also surfaces the active
trace id (so we can echo it in API responses and audit rows).
"""

from telemetry.otel import current_trace_id, setup_telemetry, span, tracer

__all__ = ["setup_telemetry", "span", "tracer", "current_trace_id"]
