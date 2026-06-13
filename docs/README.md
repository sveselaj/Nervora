# Nervora — Documentation index

The flagship overview lives in the [repository README](../README.md). These
documents go deeper on each dimension of the reference architecture.

> **Nervora** · Secure MCP Gateway for Enterprise AI Tool Execution ·
> Internal R&D Reference Architecture (mock-first, synthetic data).

| Document | What it covers |
|----------|----------------|
| [architecture.md](architecture.md) | Components, request lifecycle, data model, abstractions |
| [security-model.md](security-model.md) | Auth, token validation contract, RBAC, PII, threat notes |
| [rbac-matrix.md](rbac-matrix.md) | Full per-tool role / classification / PII / dry-run matrix |
| [judgment-block.md](judgment-block.md) | What we deliberately do **not** allow agents to do |
| [observability.md](observability.md) | OpenTelemetry spans, trace propagation, Grafana, async retry/DLQ |
| [azure-deployment.md](azure-deployment.md) | Entra ID, Service Bus, Databricks, Container Apps, IaC |
| [demo-script.md](demo-script.md) | The 5–7 minute scripted demo flow |
| [screenshots.md](screenshots.md) | Screenshot checklist for the portfolio write-up |
| [inovativi-case-study.md](inovativi-case-study.md) | Website-ready case-study copy for inovativi.com |
| [diagrams/](diagrams/) | Architecture diagram (SVG + PNG) and its generator |
