# Nervora — Screenshots checklist

The exact screenshots needed for the portfolio and the inovativi.com case study,
in capture order. Store images under `docs/img/` and reference them from the
README / case study.

> Prep: run `make up` (full stack) then `make demo` once, so a succeeded job and
> a populated audit trail already exist. Use a clean browser window and a large
> font. Demo data is synthetic by design — nothing needs hiding.

| # | Screenshot | Where to capture it | What it must show |
|---|-----------|---------------------|-------------------|
| 1 | **README hero / project title** | README top in GitHub (or the `Nervora` title + subtitle) | Project name **Nervora**, subtitle "Secure MCP Gateway for Enterprise AI Tool Execution", R&D reference-architecture badge |
| 2 | **Architecture diagram** | `docs/diagrams/nervora-architecture.png` | The full diagram: agent → gateway pipeline → sync/async → Service Bus → worker → Databricks → audit/OTel |
| 3 | **FastAPI docs — registered tools** | `http://localhost:8000/docs` | Swagger UI listing the tool endpoints + the 7 tools via `GET /tools` |
| 4 | **Successful finance report call** | Swagger / curl response | `run_budget_variance_report` → `200`, `decision=executed`, variance result, `X-Trace-Id` header |
| 5 | **Databricks async workflow queued** | Swagger / curl response | `trigger_databricks_workflow` → `202`, `decision=queued`, a `job_id` |
| 6 | **Worker succeeded** | `GET /jobs/{job_id}` (or worker logs) | `status=succeeded`, attempts=1, the mock run result |
| 7 | **Duplicate idempotency key → same job** | Two `trigger_databricks_workflow` calls, same `Idempotency-Key` | Both responses share the **same `job_id`**; message "duplicate idempotency key" |
| 8 | **Sales Agent denied from HR tool** | `get_employee_profile` as `sales_agent` | `403`, `decision=denied`, `error_code=role_not_permitted` |
| 9 | **HR PII redacted** | `get_employee_profile` as `hr_agent` | `200`, fields `salary`/`national_id`/`email`/`phone`/`address` = `***REDACTED***`, `redaction_status=redacted` |
| 10 | **CRM dry-run with human approval required** | `create_crm_update_dry_run` as `sales_agent` | `200`, `decision=dry_run`, a `diff`, `human_approval_required: true`, `writes_applied: false`, an `approval_id` |
| 11 | **execute_crm_update blocked** | `execute_crm_update` as `admin_agent` | `403`, `decision=denied`, `error_code=tool_disabled` |
| 12 | **Audit log table with trace IDs** | Admin console (`:8080`) or `GET /audit/tool-calls` | The mix of decisions (executed/denied/dry_run/queued) with roles, redaction status and **trace ids** |
| 13 | **OpenTelemetry console spans** | `docker compose logs gateway worker` (or the otel-collector logs) | Named spans: `auth.validate`, `rbac.decision`, `pii.redaction`, `tool.execute`, `queue.publish`, `worker.execute`, `databricks.call` |

## Nice-to-have (supporting shots)

- [ ] **Admin console** (`:8080`) — tool registry + queue depth + recent calls in one view.
- [ ] **Grafana** (`:3000`) — the "Nervora — Tool Execution" dashboard.
- [ ] **`docker compose ps`** — the full stack healthy.
- [ ] **`make test`** — green suite (33 passing).
- [ ] **`make demo` terminal output** — the whole scripted flow scrolling past (good for a short screen recording).

## Capture tips

- For #4–#11, the cleanest source is the Swagger "Try it out" panel (paste a dev
  token from `make token ROLE=<role>`) or a `curl` with the response headers
  shown (`curl -i`).
- For #13, set `OTEL_EXPORTER_OTLP_ENDPOINT=` empty (or unreachable) so spans
  print to the console via the fallback exporter — easiest to screenshot.
- A 30–60s screen recording of `make demo` is worth more than any single shot;
  it shows a denial and a redaction happening live.
