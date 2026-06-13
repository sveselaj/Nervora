# Nervora — Demo script (5–7 minutes)

A narrated walkthrough that proves the enterprise controls end to end. Run it
against the local stack; the automated version is `make demo`.

## Setup (before the camera rolls)

```bash
make up            # stack: gateway :8000, worker, postgres, otel, grafana :3000, admin-web :8080
```

Open three things: the Swagger UI (<http://localhost:8000/docs>), the admin
console (<http://localhost:8080>), and a terminal.

> One command runs the whole flow: `make demo`. The steps below are the
> talk-track; each maps to a block of `apps/demo-agent/agent.py`.

## The flow

**1–2. Finance agent runs an allowed report.**
The finance agent calls `run_budget_variance_report(FIN-100, 2024-Q2)`. The
gateway authenticates the token, RBAC allows it (finance is permitted), the tool
reads structured data via the Databricks **SQL mock**, and returns budget vs
actual variance. → `HTTP 200, decision=executed`.

> Talking point: the agent never touched Databricks credentials — it asked for a
> capability and the gateway executed it.

**3–4. Finance agent triggers a Databricks workflow → queued.**
`trigger_databricks_workflow(nightly_budget_rollup)` is declared **async**, so
the gateway does **not** run it inline. It reserves an idempotency key, writes an
`async_jobs` row, publishes to the queue and returns `HTTP 202, decision=queued`
with a `job_id`.

> Talking point: long-running work can't block the request path, and it can't run
> without an idempotency key.

**5–6. Worker processes the job; audit + trace visible.**
The worker pulls the message, runs the (mock) Databricks job, marks the job
`succeeded`. Poll `GET /jobs/{job_id}` → `succeeded`. Show the audit trail
(`GET /audit/tool-calls` or the admin console): every call so far is there with
its `trace_id`, decision, role and latency. Copy a `trace_id` and note it ties
the response, the spans, and the audit row together.

**(bonus) Idempotency.** Re-submit the workflow with the *same* `Idempotency-Key`.
→ same `job_id`, no second execution. "Retries are safe."

**7. Sales agent attempts HR access → denied.**
The sales agent calls `get_employee_profile(E-1001)`. → `HTTP 403,
decision=denied, error_code=role_not_permitted`. Show that the denial is in the
audit log (denied calls are first-class events).

**7b. HR agent reads the same profile → allowed, but PII redacted.**
Same tool, HR role. → `HTTP 200`, but `salary`, `national_id`, `email`, `phone`,
`address` come back `***REDACTED***`. `redaction_status=redacted`.

> Talking point: authorisation and data-minimisation are separate controls — the
> right role still doesn't get raw PII by default.

**8. Sales agent creates a CRM update dry-run.**
`create_crm_update_dry_run(ACC-300, {tier: gold})` → `HTTP 200,
decision=dry_run`. Returns a **diff** (`silver → gold`),
`writes_applied=false`, `human_approval_required=true`, and an `approval_id`. No
data was changed.

**9. Destructive execution is blocked without approval.**
`execute_crm_update(...)` → `HTTP 403, decision=denied, error_code=tool_disabled`
— the destructive tool is hard-disabled in demo mode, and even when enabled would
require an approval token + an approved approval record.

## Close

Point at the [judgment block](judgment-block.md): "Here are the eight things we
deliberately don't let the agent do — each one is enforced in code and covered by
a test, and you just watched five of them fire."

## Reset

```bash
make down          # stops the stack and removes volumes
```
