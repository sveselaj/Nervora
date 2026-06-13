# Nervora — inovativi.com case study (website-ready copy)

> Copy blocks below are ready to drop into the portfolio/case-study section of
> inovativi.com. Positioning is deliberately honest: **Internal R&D Reference
> Architecture**, mock-first, no production claims. The architecture diagram is
> at `docs/diagrams/nervora-architecture.png`.

---

## Card (portfolio grid)

**Card title**
Nervora — Secure MCP Gateway

**Card description**
A reference architecture for governing how enterprise AI agents call business
tools: OIDC authentication, tool-level RBAC, PII redaction, audit logging,
dry-run for destructive actions, and async execution with idempotency and
dead-letter handling — built around FastAPI, Azure, and Databricks patterns.

**Card tag**
Internal R&D Reference Architecture · Enterprise AI Governance

---

## Long case study

### Title
**Nervora: A Governed Gateway for Enterprise AI Tool Execution**

### Executive summary
Nervora is an internal R&D reference architecture that demonstrates how
autonomous AI agents can safely call real business tools through a governed
integration layer. Instead of handing an agent credentials and hoping for the
best, Nervora gives it *capabilities* — named, declared tools — and enforces a
strict control plane on every call: authentication, tool-level role-based access
control, PII redaction, full audit logging, dry-run gating for destructive
actions, and asynchronous execution with idempotency and retry/dead-letter
handling. It is built on the patterns we apply in enterprise AI integration
work — FastAPI, Azure Entra ID, Azure Service Bus, Databricks, PostgreSQL and
OpenTelemetry — and runs end-to-end on a laptop with mock connectors so the
governance model can be inspected and trusted before any real system is touched.

### Problem
Enterprises that want to put AI agents to work quickly hit the same wall: an
agent that can *act* is an agent that can act *wrongly*. The hard part is not
calling a model — it is everything around the call. Who is allowed to invoke
this tool? Was sensitive data exposed to the model? Can a destructive write
happen without a human in the loop? What happens when a long-running job is
retried and fires twice? And crucially — can any of it be proven after the fact?
Most demos skip this control plane entirely. For regulated, data-sensitive
organisations (especially in the DACH market), that gap is exactly what blocks
AI from moving past the prototype stage.

### Solution
Nervora makes the control plane the product. Every agent request flows through a
single governed pipeline in a fixed, audited order:

1. **Authenticate** the bearer token (Azure Entra ID / OIDC in production; signed
   dev tokens locally).
2. **Authorise** against a deny-by-default, tool-level RBAC matrix — admin is not
   a wildcard, and denials are logged.
3. **Validate** arguments against the tool's typed schema.
4. **Route** by classification — read tools run synchronously; long-running tools
   are queued; dry-run tools return a diff and require approval; destructive
   tools are denied unless explicitly approved.
5. **Redact PII** before any output is visible to the model.
6. **Audit** every outcome — allowed, denied, dry-run, queued, executed, failed —
   in the same transaction as the action.

The result is a system where the *safe* path is the *only* path.

### Architecture highlights
- **Monorepo of single-responsibility packages** (auth, rbac, audit, pii,
  telemetry, tool registry, Databricks connector, Service Bus abstraction)
  composed by two services: the FastAPI gateway and an async worker.
- **Swap local ↔ Azure by configuration, not code.** Three interfaces —
  `TokenVerifier`, `MessageQueue`, `DatabricksConnector` — each have a local/mock
  implementation and a production implementation (Entra ID JWKS, Azure Service
  Bus, real Databricks SQL/Jobs APIs).
- **Mock-first connectors** let the entire flow — including the async
  queue→worker→Databricks path — run offline and deterministically.
- **Infrastructure as Code** for the Azure target topology (Container Apps,
  PostgreSQL Flexible Server, Service Bus, Application Insights) in both
  Terraform and Bicep.

### Security and governance highlights
- **Capabilities, not credentials** — the agent never holds a database
  connection or a Databricks token.
- **Tool-level RBAC, deny-by-default** — four agent personas (HR, Finance, Sales,
  Admin) mapped to Entra ID app roles; access is explicit per tool.
- **PII redaction boundary** — declared sensitive fields are masked and a regex
  sweep catches leakage through free-text, before output reaches the model.
- **Destructive-action gate** — the destructive tool is disabled by default and,
  when enabled, requires a valid approval token *and* an approved approval
  record created via a prior dry-run.
- **Tamper-evident audit** — a single sanctioned writer records every decision;
  there is no side-effecting path that skips the audit log.

### Observability highlights
- **OpenTelemetry spans** wrap every stage: auth, RBAC, PII redaction, tool
  execution, queue publish, worker execution, the Databricks call and each audit
  write.
- **One trace id** is returned in the response header (`X-Trace-Id`) and stored
  on every audit and job record — so a single id ties an API response to its
  spans and its audit trail.
- **Grafana + OTel Collector** ship in the local stack; an admin console renders
  the live tool registry, queue depth and audit trail.

### Demo flow (5–7 minutes)
A finance agent runs an allowed budget-variance report (read via the Databricks
SQL mock), then triggers a Databricks workflow that is *queued* — the agent
cannot run it synchronously — and processed by the worker to completion. A
duplicate submission with the same idempotency key returns the original job
without re-executing. A sales agent is then **denied** access to an HR tool, an
HR agent reads the same employee profile but receives **redacted** PII, a CRM
update runs as a **dry-run** returning a diff and "human approval required", and
a destructive write is **blocked**. The full audit trail — with trace ids — is
shown throughout.

### What agents are deliberately not allowed to do
1. Execute destructive write actions without explicit approval.
2. Bypass tool-level RBAC.
3. Access raw PII unless policy allows it.
4. Trigger long-running jobs synchronously.
5. Retry non-idempotent actions without an idempotency key.
6. Call hidden tools outside the published registry.
7. Write directly to production systems in demo mode.
8. Suppress audit logging.

Each of these is enforced in code and covered by an automated test.

### Technical stack
Python 3.12 · FastAPI · Pydantic · SQLAlchemy 2.0 · PostgreSQL ·
Azure Entra ID / OIDC (PyJWT + JWKS) · Azure Service Bus (with a local
Postgres-backed queue for offline runs) · Databricks SQL Statement Execution &
Jobs APIs (mock-first) · OpenTelemetry · Grafana · Docker Compose ·
Terraform & Bicep · Pytest.

### Status / honest limitations
Nervora is an **Internal R&D Reference Architecture**, not a deployed product. It
is mock-first by design: the Databricks and Azure Service Bus connectors run as
local/mock backends out of the box, with the production implementations present
as prepared, documented interfaces. PII redaction is policy- and pattern-based
defence-in-depth, not an absolute guarantee. The Infrastructure as Code is
reference-grade — production networking, secret management (Key Vault) and
identity hardening are documented but not fully implemented. The patterns it
demonstrates are extracted from real enterprise AI integration work; the
implementation here uses synthetic data and touches no production systems.

### Suggested CTA
**Building AI agents that need to touch real enterprise systems?**
Let's talk about the governance layer. Nervora shows the patterns we use to make
agentic AI auditable, access-controlled and safe for regulated environments —
[get in touch](https://inovativi.com/contact) to discuss applying them to your
stack.
