# Nervora — Security model

## Principle: capabilities, not credentials

The agent is issued a bearer token that asserts an **agent role**. It never
holds a database connection string, a Databricks token, or a Service Bus key.
Every action it can take is a named tool in the published registry, gated by the
gateway. Removing the gateway removes the agent's ability to do anything.

## Authentication

Tokens are validated by a `TokenVerifier` selected via `AUTH_MODE`:

### Local development — `DevTokenVerifier` (HS256)
- Symmetric secret (`DEV_TOKEN_SIGNING_SECRET`).
- The `demo-agent` mints tokens with `DevTokenSigner`, mirroring the exact claim
  shape Entra ID emits (`sub`, `agent_id`, `agent_role`, `scp`, `aud`, `exp`…).
- **For local development only.** Never enabled in production.

### Production — `EntraOIDCVerifier` (RS256 / JWKS)
Validation contract (all enforced):
1. Signature verified against the tenant's rotating signing keys from
   `ENTRA_JWKS_URL` (cached/refreshed by `PyJWKClient`).
2. `aud` matches `ENTRA_AUDIENCE` (the gateway's API app registration).
3. `iss` matches `ENTRA_ISSUER` (`https://login.microsoftonline.com/<tid>/v2.0`).
4. `exp` / `iat` present and valid (clock-skew tolerant).
5. The agent role is taken from an app role / group claim (`agent_role`/`role`).

Auth failures return `401` and are not treated as tool calls.

> Map agent personas to **Entra ID app roles**. Issue tokens via the client
> credentials or on-behalf-of flow so the human `sub` and the acting `agent_id`
> are both present and auditable.

## Authorisation — tool-level RBAC

- **Deny by default.** A role must be explicitly listed in a tool's
  `required_roles`. (`packages/rbac/policy.py`.)
- **Admin is not a wildcard.** The admin role is listed explicitly on the tools
  it may call, so the matrix stays fully auditable — there is no implicit
  super-role.
- **Disabled tools are denied for everyone**, regardless of role (kill-switch).
- Every denial is written to `tool_calls` (decision=`denied`) and
  `audit_events`, with the machine-readable reason code.

## Destructive-action gate

`execute_crm_update` is `classification=destructive`. It passes only if, in order:

1. the tool is **enabled** (it is hard-disabled in `demo` mode);
2. a valid `X-Approval-Token` matching the configured `ADMIN_APPROVAL_TOKEN` is
   presented; **and**
3. the referenced approval record exists and is in `approved` state (created via
   a prior dry-run and approved out-of-band by the admin role).

Any failure → `denied`, logged. The dry-run tool (`create_crm_update_dry_run`)
**never writes** — it returns a diff and creates a `pending` approval.

## PII redaction (before model-visible output)

Two layers (`packages/pii`):

1. **Declared fields** — a tool declares `sensitive_fields` (e.g. `salary`,
   `national_id`, `email`); these are masked unless the caller's role is in the
   tool's `raw_pii_roles`. In the reference config `raw_pii_roles` is empty, so
   `get_employee_profile` returns redacted PII to *everyone*, including HR.
2. **Pattern sweep** — every remaining string is scanned for email / phone /
   IBAN / SSN-like / card-like patterns as defence-in-depth against leaks
   through free-text fields. This runs even when raw access is allowed.

The `tool_calls.redaction_status` column records `none` vs `redacted` per call.

## Audit integrity

`AuditRepository` is the only sanctioned writer, and the gateway records a
`tool_calls` row + an `audit_events` row on **every** path — allowed, denied,
dry-run, queued, executed, failed — inside the same transaction as the action.
There is no code path that performs a tool side effect without an audit write,
which is what makes "agents cannot suppress audit logging" enforceable.

## Idempotency & replay safety

Async/non-idempotent actions carry an idempotency key (client-supplied via
`Idempotency-Key` or gateway-generated). The key is reserved before the job is
queued; a duplicate submission returns the original job, and the worker skips
re-execution if the key is already `completed`. This prevents double-triggering
a Databricks workflow on retries or client replays.

## Transport & secret notes (production)

- Terminate TLS at ingress; the gateway is HTTP behind it.
- Store `DATABASE_URL`, Service Bus connection string and Databricks token as
  secret references (Key Vault), not inline env — see the IaC TODOs.
- Prefer managed identity for Service Bus / Postgres over connection strings.
- The permissive CORS policy is **demo-only** (`APP_ENV=demo`); production serves
  the console same-origin / behind an auth proxy.

## Known threat-model gaps (honest)

- Redaction is heuristic; a determined exfiltration via a tool's free-text could
  evade the regex sweep. Treat sensitive tools as `sensitive` and minimise
  free-text outputs.
- No per-tool rate limiting / quota in this reference (add at ingress or in the
  executor).
- Dev token path is intentionally weak and must stay out of production.
