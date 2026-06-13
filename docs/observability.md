# Nervora — Observability

## Tracing

OpenTelemetry spans wrap every stage of the pipeline. Span names:

| Span | Where | Attributes |
|------|-------|------------|
| `auth.validate` | gateway dependency | — |
| `rbac.decision` | executor | `tool`, `role` |
| `pii.redaction` | executor | `tool`, `allow_raw` |
| `tool.execute` | executor (sync/dry-run/destructive) | `tool`, `mode` |
| `queue.publish` | executor (async) | `tool`, `job_id` |
| `worker.execute` | worker | `tool`, `job_id` |
| `databricks.call` | mock/real connector path (within `tool.execute`/`worker.execute`) | — |
| audit writes | within the same span context | — |

FastAPI is auto-instrumented (`opentelemetry-instrumentation-fastapi`) so each
HTTP request is a parent span; the stage spans nest under it.

## Trace propagation into responses and audit

- Every `POST /tools/{tool}/invoke` response carries `X-Trace-Id` and
  `X-Request-Id` headers, and the body includes `trace_id`.
- The same `trace_id` is stored on `tool_calls`, `audit_events` and `async_jobs`.
- Result: one id ties an API response → its spans → its audit/job records. This
  is the demo's "show me the trace" moment.

## Exporters

`packages/telemetry/otel.py` configures a `TracerProvider` that:

- exports OTLP/gRPC to `OTEL_EXPORTER_OTLP_ENDPOINT` when set (the
  `otel-collector` service in compose), **or**
- falls back to console span export when no collector is reachable
  (`OTEL_CONSOLE_FALLBACK=true`), **or**
- degrades to a no-op if the SDK is unavailable — tracing never breaks the app.

The collector config (`infra/otel-collector.yaml`) receives OTLP on 4317/4318,
batches, logs spans (debug exporter) and exposes Prometheus-format metrics on
`:8889`.

## Grafana

- Provisioned automatically in compose (`infra/grafana/provisioning`).
- Dashboard JSON: `infra/grafana/dashboards/secure-mcp-gateway.json` — panels for
  tool calls by decision, execution latency p50/p95, denied calls, queued jobs,
  and dead-letter count.
- Anonymous admin at <http://localhost:3000>.

> The dashboard's PromQL targets assume span-derived metrics (e.g. via a
> span-metrics connector or app-emitted metrics named `tool_calls_total`,
> `tool_latency_ms_bucket`, `jobs_dead_letter_total`). Out of the box the demo
> ships traces; wiring a metrics pipeline / Tempo backend is on the roadmap. The
> live numbers are always available from the audit endpoints and the admin
> console regardless.

## Async retry / DLQ contract

This contract is identical across the local queue and Azure Service Bus.

- **Visibility timeout / peek-lock** — `receive` locks a message and makes it
  invisible for the timeout; if the worker crashes mid-process, the lock lapses
  and the message is redelivered.
- **Retry** — on failure the worker `abandon`s the message; it becomes
  immediately eligible for redelivery and `delivery_count` increments.
- **Dead-letter** — once `delivery_count` reaches `QUEUE_MAX_DELIVERY_COUNT`
  (default 5), the message is dead-lettered and the `async_jobs` row is marked
  `dead_letter` with the error code/detail. Non-retryable errors (e.g. unknown
  tool) are dead-lettered immediately.
- **Duplicate detection** — the worker checks the idempotency key before
  executing; a key already `completed` means the job ran before, so the message
  is settled without re-execution.

Inspect queue depth and DLQ count via `GET /queue/stats` (local backend) or the
admin console; on Azure use the portal / `Monitor`.
