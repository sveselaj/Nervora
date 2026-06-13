"""Nervora demo agent CLI.

Mints local dev tokens for the four agent personas and drives the scripted
reference flow against a running Nervora gateway. This is a *client* — it has no special
privileges; everything it can do is gated by the gateway exactly as a real
agent would be.

Usage:
    python apps/demo-agent/agent.py token --role finance_agent
    python apps/demo-agent/agent.py demo
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

# Make the shared packages importable when run directly from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))

from auth import DevTokenSigner  # noqa: E402
from common.settings import get_settings  # noqa: E402

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000")

PERSONAS = {
    "hr_agent": ("user-hr@inovativi.example", "agent-hr-001"),
    "finance_agent": ("user-fin@inovativi.example", "agent-fin-001"),
    "sales_agent": ("user-sales@inovativi.example", "agent-sales-001"),
    "admin_agent": ("user-admin@inovativi.example", "agent-admin-001"),
}


def mint(role: str) -> str:
    settings = get_settings()
    signer = DevTokenSigner(
        secret=settings.dev_token_signing_secret, audience=settings.entra_audience
    )
    subject, agent_id = PERSONAS.get(role, (f"user-{role}", f"agent-{role}"))
    return signer.mint(subject=subject, agent_id=agent_id, role=role,
                       scopes=["tools.invoke"])


def _headers(role: str, *, approval_token: str | None = None,
             idempotency_key: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {mint(role)}"}
    if approval_token:
        h["X-Approval-Token"] = approval_token
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return h


def _call(client: httpx.Client, role: str, tool: str, arguments: dict, **kw) -> httpx.Response:
    return client.post(
        f"{GATEWAY_URL}/tools/{tool}/invoke",
        json={"arguments": arguments},
        headers=_headers(role, **kw),
    )


def _show(label: str, resp: httpx.Response) -> dict:
    data = resp.json()
    print(f"\n=== {label} ===")
    print(f"HTTP {resp.status_code} | decision={data.get('decision')} "
          f"| trace_id={data.get('trace_id')}")
    if data.get("error_code"):
        print(f"  error_code: {data['error_code']} — {data.get('message')}")
    if data.get("redaction", {}).get("status") == "redacted":
        print(f"  redacted_fields: {data['redaction'].get('redacted_fields')}")
    if data.get("job_id"):
        print(f"  job_id: {data['job_id']}")
    if data.get("approval_id"):
        print(f"  approval_id: {data['approval_id']}")
    if data.get("result"):
        import json
        print("  result:", json.dumps(data["result"], indent=2)[:800])
    return data


def run_demo() -> None:
    with httpx.Client(timeout=15.0) as client:
        print(f"Gateway: {GATEWAY_URL}")
        print("Tools:", [t["name"] for t in client.get(f"{GATEWAY_URL}/tools").json()])

        # 1-2. Finance agent runs an allowed budget variance report.
        _show("1. Finance Agent -> run_budget_variance_report (allowed)",
              _call(client, "finance_agent", "run_budget_variance_report",
                    {"department_id": "FIN-100", "period": "2024-Q2"}))

        # 3-4. Finance agent triggers a Databricks workflow -> queued async.
        queued = _show("3. Finance Agent -> trigger_databricks_workflow (queued async)",
                       _call(client, "finance_agent", "trigger_databricks_workflow",
                             {"workflow_name": "nightly_budget_rollup",
                              "parameters": {"period": "2024-Q2"}},
                             idempotency_key="demo-key-001"))

        # 5-6. Worker processes the job; poll status until terminal.
        job_id = queued.get("job_id")
        if job_id:
            print("\n=== 5. Worker processes job (polling status) ===")
            for _ in range(20):
                job = client.get(f"{GATEWAY_URL}/jobs/{job_id}",
                                 headers=_headers("finance_agent")).json()
                print(f"  job {job_id}: status={job['status']} attempts={job['attempts']}")
                if job["status"] in ("succeeded", "failed", "dead_letter"):
                    break
                time.sleep(1.0)

        # Idempotency: re-submit with the same key -> same job, no new work.
        _show("3b. Duplicate submit (same Idempotency-Key) -> returns existing job",
              _call(client, "finance_agent", "trigger_databricks_workflow",
                    {"workflow_name": "nightly_budget_rollup",
                     "parameters": {"period": "2024-Q2"}},
                    idempotency_key="demo-key-001"))

        # 7. Sales agent attempts HR access -> denied by RBAC.
        _show("7. Sales Agent -> get_employee_profile (DENIED by RBAC)",
              _call(client, "sales_agent", "get_employee_profile", {"employee_id": "E-1001"}))

        # HR agent reads the profile -> allowed, but PII redacted by default.
        _show("7b. HR Agent -> get_employee_profile (allowed, PII redacted)",
              _call(client, "hr_agent", "get_employee_profile", {"employee_id": "E-1001"}))

        # 8. Sales agent creates a CRM update dry-run -> diff + approval required.
        _show("8. Sales Agent -> create_crm_update_dry_run (dry-run, no writes)",
              _call(client, "sales_agent", "create_crm_update_dry_run",
                    {"account_id": "ACC-300", "proposed_changes": {"tier": "gold"}}))

        # 9. Destructive execution blocked without approval (disabled in demo).
        _show("9. Admin Agent -> execute_crm_update (BLOCKED, destructive/disabled)",
              _call(client, "admin_agent", "execute_crm_update",
                    {"account_id": "ACC-300", "approved_change_id": "apr_does_not_exist"}))

        print("\n=== Audit trail (most recent) ===")
        calls = client.get(f"{GATEWAY_URL}/audit/tool-calls?limit=12",
                           headers=_headers("admin_agent")).json()
        for c in calls:
            print(f"  {c['created_at']} | {c['tool_name']:<28} | role={c['role']:<14} "
                  f"| decision={c['decision']:<9} | redaction={c['redaction_status']} "
                  f"| trace={c['trace_id'][:12]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nervora — Secure MCP Gateway demo agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    tok = sub.add_parser("token", help="mint a dev token for a role")
    tok.add_argument("--role", default="finance_agent", choices=list(PERSONAS))
    sub.add_parser("demo", help="run the scripted demo flow")
    args = parser.parse_args()

    if args.cmd == "token":
        print(mint(args.role))
    elif args.cmd == "demo":
        run_demo()


if __name__ == "__main__":
    main()
