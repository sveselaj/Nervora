# Nervora — What we deliberately do **not** allow agents to do

This is the project's judgment block — the explicit boundary of agent authority.
Each item is enforced in code and covered by a test.

### 1. Agents cannot execute destructive write actions without explicit approval
`execute_crm_update` is `classification=destructive`. It is **disabled in demo
mode** and, when enabled, requires (a) a valid `X-Approval-Token` and (b) an
approval record in `approved` state. Default behaviour is to reject.
→ `Executor._handle_destructive`; tests `test_execute_crm_update_blocked_in_demo`,
`test_destructive_execution_when_enabled_requires_approved_record`,
`test_destructive_blocked_403`.

### 2. Agents cannot bypass tool-level RBAC
Authorisation is deny-by-default; a role must be explicitly listed in a tool's
`required_roles`. Admin is not a wildcard. Denials are logged.
→ `rbac.evaluate`; tests `test_gateway_denies_cross_domain_and_logs`,
`test_sales_denied_hr_returns_403`, `test_admin_not_implicitly_granted_everything`.

### 3. Agents cannot access raw PII unless policy allows it
Sensitive fields are masked before output is model-visible; a regex sweep
catches free-text leakage. The reference config grants no role raw PII.
→ `pii.redact`; tests `test_employee_profile_redacted_by_default`,
`test_declared_sensitive_fields_masked`.

### 4. Agents cannot trigger long-running jobs synchronously
`trigger_databricks_workflow` is `execution_mode=async`; the gateway only ever
queues it (HTTP 202) and a worker executes it out of band.
→ `Executor._handle_async`; test `test_async_tool_is_queued_not_run_sync`.

### 5. Agents cannot retry non-idempotent actions without an idempotency key
Async jobs carry an idempotency key (supplied or gateway-generated). It is
reserved before queueing; duplicates return the original job and the worker
skips re-execution of a completed key.
→ `Executor._handle_async`, `Worker._process` idempotency guard; tests
`test_duplicate_idempotency_key_returns_same_job`,
`test_idempotency_prevents_duplicate_execution_on_redelivery`.

### 6. Agents cannot call hidden tools outside the published tool registry
The registry is the only source of callable tools; an unknown tool name is an
explicit `denied`/`UNKNOWN_TOOL`, never a silent no-op. `GET /tools` publishes
the full set.
→ `Executor.invoke` unknown-tool branch; test `test_unknown_tool_denied_not_silent`.

### 7. Agents cannot write directly to production systems in demo mode
All tool data is synthetic; the destructive tool is disabled; the CRM tool is
dry-run-only; Databricks and Service Bus run as mock/local backends.
→ `build_default_registry(demo_mode=True)`; `DATABRICKS_MODE=mock`,
`QUEUE_BACKEND=local`.

### 8. Agents cannot suppress audit logging
`AuditRepository` is the only sanctioned writer and the gateway records a
`tool_calls` + `audit_events` row on **every** path (allowed/denied/dry_run/
queued/executed/failed) in the same transaction as the action. No side-effecting
path skips the audit write.
→ `Executor.invoke` `finish()`; verified by the denial-logging assertions in the
RBAC tests.
