# Nervora — Architecture

## Goals

Demonstrate the **control plane** between an autonomous AI agent and enterprise
systems of record. The agent receives *capabilities* (named, declared tools),
never *credentials*. The gateway is the single chokepoint where authentication,
authorisation, redaction, async decoupling and audit are enforced.

## Components

| Component | Responsibility |
|-----------|----------------|
| `apps/mcp-gateway` | FastAPI service. Hosts the tool registry and the governed `Executor` pipeline. The only entrypoint agents talk to. |
| `apps/worker` | Long-poll worker. Pulls async jobs off the queue, enforces idempotency, executes tool handlers, drives retry/DLQ. |
| `apps/demo-agent` | A thin client. Mints dev tokens and exercises the gateway exactly as a real agent would. |
| `apps/admin-web` | Static, read-only operator console over the public audit/policy endpoints. |
| `packages/*` | Shared libraries — see the README layout table. Each is a single-responsibility module the gateway and worker compose. |

## Request lifecycle (sync tool)

```
client ──bearer──▶ FastAPI route
                     │  Depends(get_principal)         span: auth.validate
                     ▼
                   Executor.invoke
                     ├─ RBAC.evaluate                  span: rbac.decision
                     ├─ ToolSpec.validate_args
                     ├─ ToolSpec.run(ctx, args)        span: tool.execute
                     ├─ pii.redact(output)             span: pii.redaction
                     └─ AuditRepository.record_*        (tool_calls + audit_events)
                     ▼
                   InvokeResponse  (+ X-Trace-Id, X-Request-Id headers)
```

## Request lifecycle (async tool)

```
client ─▶ Executor.invoke
            ├─ RBAC + validate
            ├─ reserve idempotency_key
            ├─ create async_jobs row (status=queued)
            └─ queue.publish({job_id, idempotency_key, tool_name, args})  span: queue.publish
          ◀─ 202 { decision: queued, job_id }

worker loop ─▶ queue.receive (peek-lock, visibility timeout)
                ├─ idempotency guard (skip if key completed)   span: worker.execute
                ├─ job → running
                ├─ ToolSpec.run(ctx, args)  (e.g. Databricks job)  span: databricks.call
                ├─ success → job succeeded, idempotency completed, queue.complete
                └─ failure → retry (abandon) or dead-letter at max delivery
```

The agent **cannot** run the long job synchronously: `trigger_databricks_workflow`
is declared `execution_mode=async`, so the gateway only ever queues it.

## Data model

Six tables (PostgreSQL in deployment, SQLite in tests). DDL:
[`packages/audit/schema.sql`](../packages/audit/schema.sql); ORM:
[`packages/audit/models.py`](../packages/audit/models.py).

- **audit_events** — append-only event stream (decisions, job lifecycle, approvals).
- **tool_calls** — one row per invocation: trace_id, request_id, user/agent/role,
  tool, input_hash, redaction_status, decision, error_code, latency_ms.
- **tool_policies** — a queryable snapshot of each tool's declared policy,
  refreshed from the registry on startup.
- **async_jobs** — job records with status, attempts, result, error.
- **approvals** — human-approval records created by dry-runs and consumed by
  destructive executions.
- **idempotency_keys** — reserve/complete guard preventing duplicate execution.
- *(plus `queue_messages`)* — backing table for the local queue backend only.

`input_hash` is a SHA-256 over `{tool, args}`, so the audit trail proves *what*
was requested without persisting potentially-sensitive payloads.

## Key abstractions (swap local ↔ Azure by config)

- **TokenVerifier** — `DevTokenVerifier` (HS256) ↔ `EntraOIDCVerifier`
  (RS256/JWKS). Selected by `AUTH_MODE`.
- **MessageQueue** — `LocalQueue` (Postgres/SQLite, peek-lock semantics) ↔
  `AzureServiceBusQueue`. Selected by `QUEUE_BACKEND`.
- **DatabricksConnector** — `MockDatabricksConnector` ↔ `RealDatabricksConnector`
  (SQL Statement Execution + Jobs 2.1). Selected by `DATABRICKS_MODE`.

The gateway and worker depend only on the interfaces, so production is a
configuration change, not a code change.

## Why a `common` package

`common` holds only the wiring both the gateway and worker must agree on —
typed `Settings` (so policy decisions are consistent across process
boundaries) and id/hash helpers. No business logic lives there.

## Tool design contract

A `ToolSpec` is a declarative policy object plus a `run` callable. Governance
(auth, RBAC, PII, async, dry-run, approval) lives entirely in the gateway and
worker — **never inside a tool**. A tool handler contains only business logic
and may raise `ToolError(code=...)`, which is captured into the audit trail. New
tools are added by registering a `ToolSpec`; there is no other way to make a
tool callable, which is what makes "no hidden tools" enforceable.
