"""OpenTelemetry tracer configuration.

Designed to never break the app: if the OTel SDK or an exporter is missing or
unreachable, tracing degrades to a no-op (or console output) instead of raising.
That keeps the reference architecture runnable on a laptop with nothing else
installed while still emitting real spans when a collector is present.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

_INITIALISED = False

try:  # The SDK is a hard dependency, but stay defensive for minimal installs.
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - only on broken installs
    _OTEL_AVAILABLE = False


def setup_telemetry(
    *,
    service_name: str,
    otlp_endpoint: str = "",
    enabled: bool = True,
    console_fallback: bool = True,
) -> None:
    """Idempotently configure the global tracer provider."""
    global _INITIALISED
    if _INITIALISED or not _OTEL_AVAILABLE or not enabled:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exported = False
    if otlp_endpoint:
        with contextlib.suppress(Exception):
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
            )
            exported = True

    if not exported and console_fallback:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _INITIALISED = True


def tracer(name: str = "secure-mcp-gateway"):
    if not _OTEL_AVAILABLE:
        return None
    from opentelemetry import trace

    return trace.get_tracer(name)


@contextlib.contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Start a span. No-op when OTel is unavailable."""
    if not _OTEL_AVAILABLE:
        yield None
        return
    from opentelemetry import trace

    t = trace.get_tracer("secure-mcp-gateway")
    with t.start_as_current_span(name) as sp:
        if attributes:
            for k, v in attributes.items():
                with contextlib.suppress(Exception):
                    sp.set_attribute(k, v)
        yield sp


def current_trace_id() -> str | None:
    """Return the active span's trace id as 32-char hex, if any."""
    if not _OTEL_AVAILABLE:
        return None
    from opentelemetry import trace

    ctx = trace.get_current_span().get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return None
