# Nervora — Azure deployment

The reference architecture runs entirely offline (mock/local backends). Moving
to Azure flips three switches via configuration — **no application code
changes** — because the gateway and worker depend only on the
`TokenVerifier` / `MessageQueue` / `DatabricksConnector` interfaces.

| Capability | Local default | Azure production |
|------------|---------------|------------------|
| Auth | `AUTH_MODE=dev` (HS256) | `AUTH_MODE=entra` (Entra ID JWKS / RS256) |
| Async queue | `QUEUE_BACKEND=local` (Postgres) | `QUEUE_BACKEND=azure` (Service Bus) |
| Databricks | `DATABRICKS_MODE=mock` | `DATABRICKS_MODE=real` (SQL + Jobs APIs) |
| Database | docker Postgres | Azure DB for PostgreSQL Flexible Server |
| Tracing | console / local collector | Application Insights (OTLP) |

## Target topology

```
Entra ID ──validates tokens──┐
                             ▼
            Azure Container Apps environment
            ├─ gateway  (external ingress, :8000)
            └─ worker   (internal, scales on queue length / KEDA)
                 │
   ┌─────────────┼───────────────────────────────┐
   ▼             ▼                                 ▼
 PostgreSQL   Service Bus (queue: tool-jobs)   Application Insights
 Flexible     max_delivery=5, DLQ, lock 30s    (+ Log Analytics)
 Server
```

## 1. Entra ID (authentication)

1. Register an **API** app registration for the gateway; set the Application ID
   URI to `api://secure-mcp-gateway` (→ `ENTRA_AUDIENCE`).
2. Define **app roles**: `hr_agent`, `finance_agent`, `sales_agent`,
   `admin_agent`. Assign them to the agent service principals.
3. Issue tokens via client-credentials (or on-behalf-of for a human-in-the-loop)
   so both `sub` and the acting `agent_id` are present.
4. Configure the gateway:
   ```
   AUTH_MODE=entra
   ENTRA_TENANT_ID=<tenant-guid>
   ENTRA_AUDIENCE=api://secure-mcp-gateway
   ENTRA_ISSUER=https://login.microsoftonline.com/<tenant-guid>/v2.0
   ENTRA_JWKS_URL=https://login.microsoftonline.com/<tenant-guid>/discovery/v2.0/keys
   ```
   `EntraOIDCVerifier` then verifies signature (JWKS), `aud`, `iss`, `exp`/`iat`.

## 2. Service Bus (async)

- Provisioned by the IaC with `max_delivery_count=5`, `lock_duration=PT30S`,
  `default_message_ttl=P1D`, dead-lettering on expiry — matching the worker's
  retry/DLQ contract exactly.
- Set `QUEUE_BACKEND=azure` and supply `SERVICEBUS_CONNECTION_STRING` (prefer a
  Key Vault secret reference / managed identity).
- `AzureServiceBusQueue` maps `complete`/`abandon`/`dead_letter` onto native
  peek-lock settlement; the broker auto-dead-letters at max delivery.

## 3. Databricks (real connector)

- Set `DATABRICKS_MODE=real` + `DATABRICKS_HOST`, `DATABRICKS_TOKEN`,
  `DATABRICKS_WAREHOUSE_ID`.
- `RealDatabricksConnector` targets the SQL Statement Execution API
  (`/api/2.0/sql/statements`) and Jobs API 2.1 (`/api/2.1/jobs/run-now`). The
  call/poll bodies are documented inline; implement + add integration tests
  behind the flag before relying on it.

## 4. Infrastructure as Code

Two equivalent options under `infra/`:

- **Terraform** (`infra/terraform/main.tf`) — resource group, PostgreSQL
  Flexible Server, Service Bus namespace + queue, Container Apps env + gateway +
  worker, Log Analytics + Application Insights. See its README for `plan`/`apply`.
- **Bicep** (`infra/bicep/main.bicep`) — the same topology for ARM/Bicep teams.

Both inject `DATABASE_URL` and the Service Bus connection string as Container
App **secrets** and set the production env (`APP_ENV=prod`, `AUTH_MODE=entra`,
`QUEUE_BACKEND=azure`).

## Production hardening checklist (not fully implemented — be honest)

- [ ] Private endpoints / VNet integration for Postgres + Service Bus.
- [ ] Key Vault references for all secrets (replace inline secret values).
- [ ] Managed identity instead of connection strings where supported.
- [ ] KEDA scale rule on Service Bus queue length for the worker.
- [ ] WAF / API Management in front of the gateway ingress; per-tool rate limits.
- [ ] Restrict CORS (the permissive policy is demo-only).
- [ ] Backup/retention policy for the audit database.
