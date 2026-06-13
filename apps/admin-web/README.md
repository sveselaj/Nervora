# Nervora — Admin Web

A single-file, read-only operator console for Nervora (the Secure MCP Gateway). It calls
the gateway's public endpoints (`/healthz`, `/tools`, `/queue/stats`,
`/audit/tool-calls`) and renders:

- the published tool registry and each tool's policy,
- live queue depth (including dead-letter count),
- the most recent tool calls with their RBAC/PII decisions and trace ids.

It deliberately has **no privileges of its own** — paste a dev bearer token
(`make token ROLE=admin_agent`) to read the audit endpoints, exactly as any
client must.

In `docker compose up` it is served by nginx at <http://localhost:8080>. The
gateway enables permissive CORS in `demo` mode so the static page can call it;
in production you would serve this behind the same origin / an auth proxy.
