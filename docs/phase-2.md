# Nervora — Phase 2 Roadmap

Phase 2 builds directly on the Phase 1 **controlled execution layer**. It does
not replace any of it: the governed pipeline (auth → RBAC → validate → route →
redact → audit), the tool registry, the approval gate and the audit trail stay
as the foundation. Phase 2 hardens the human-approval path, opens standard
transports (MCP / OpenAPI) over the *existing* registry, and makes governance
and observability richer — without turning the reference architecture into a
product.

## 1. Phase 1 completed foundation

Already in place and demoable today:

- Controlled tool execution through a single governed pipeline.
- Tool-level, deny-by-default RBAC (admin is not a wildcard).
- Durable audit trail in Postgres — one record per decision, including denials.
- Approval gate: approval-required tools write nothing and return a pending
  `approval_id`; an admin-only endpoint clears it.
- `/health` (liveness) and `/health/ai` (services + full tool surface).
- Structured JSON request logging, OpenTelemetry spans, deterministic JSON
  response envelopes, env-based config, Dockerized local stack.

## 2. Phase 2 objective

Make the control plane **production-credible for human-in-the-loop governance
and standard agent interop**, while staying a small, sharp reference
architecture. Everything below extends an existing seam rather than adding a new
subsystem.

## 3. Planned capabilities

- **Signed, expiring approval tokens + admin-web approval UI.** Replace the
  static `ADMIN_APPROVAL_TOKEN` env secret with short-lived, signed tokens bound
  to a specific approval; surface pending approvals and an approve/reject action
  in the existing read-only admin-web console.
- **Native MCP transport over the existing tool registry.** Expose the current
  `ToolSpec` registry over MCP (stdio / streamable HTTP) so MCP-capable agents
  call the same governed tools. No tool logic changes — the registry is the
  source of truth.
- **Optional OpenAPI tool import.** Generate `ToolSpec` entries from an OpenAPI
  document so existing REST services become governed tools, behind a flag.
- **Policy-as-code option (OPA/Rego).** Offer OPA/Rego as an alternative policy
  engine to the in-code RBAC matrix, behind a config switch, keeping
  deny-by-default semantics and the same decision/reason shape.
- **Real connector flags.** Promote the prepared interfaces to real
  implementations behind flags: Databricks SQL/Jobs (`DATABRICKS_MODE=real`) and
  Azure Service Bus (`QUEUE_BACKEND=azure`), with integration tests gated off by
  default.
- **Richer `/health/ai` metrics + Grafana.** Add per-tool last-call
  success/error counts and latency to `/health/ai`, and wire them into the
  existing Grafana dashboard.

## 4. Implementation notes / existing seams

These capabilities map onto seams Phase 1 deliberately left open:

- **Approvals** already have a persisted `approvals` table, lifecycle states
  (`pending → approved → consumed`) and an admin-only approve endpoint — Phase 2
  adds token signing/expiry and a UI on top, not a new flow.
- **MCP / OpenAPI** ride on the single `ToolRegistry`. Tool names are already
  namespaced (`crm.*`, `billing.*`) to anticipate MCP tool namespacing.
- **Policy-as-code** swaps the body of `rbac.evaluate(...)`; the `Decision` /
  reason-code contract is stable, so callers and audit records don't change.
- **Connectors** are already abstractions (`databricks_connector`, `servicebus`)
  selected by env (`*_MODE` / `QUEUE_BACKEND`); the real classes are present as
  prepared interfaces.
- **`/health/ai`** already returns a structured per-tool registry view; the
  metrics fields slot into that same payload.

## 5. Suggested priority order

1. **Signed, expiring approval tokens + admin-web approval UI** — closes the
   most visible governance gap and is the strongest sales-demo upgrade.
2. **Native MCP transport** — the headline interop story; high signal, contained
   scope over the existing registry.
3. **Richer `/health/ai` metrics + Grafana** — small, compounds the
   observability story already in place.
4. **Real connector flags** (Databricks, Service Bus) — credibility for
   production claims, isolated behind flags and tests.
5. **Policy-as-code (OPA/Rego)** — valuable but optional; only after the matrix
   has stabilized.
6. **OpenAPI tool import** — useful breadth, lowest urgency.

## Not in scope yet

Deliberately excluded to keep Nervora a reference architecture and sales proof,
not a premature product:

- Multi-tenant isolation and usage-based billing.
- Marketplace-style tool catalogs / third-party tool publishing.
- Complex dashboarding beyond the single reference Grafana board.
- Hosted SaaS / managed deployment and its operational surface (sign-up,
  metering, SLAs).

These may be revisited later, but only once the controlled execution layer and
its interop story are proven.
