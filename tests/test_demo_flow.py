"""Phase 1 demo flow: health endpoints + the two demo tools.

Covers the four behaviours the demo flow promises end-to-end:
health checks, RBAC allow/deny, the approval gate, and audit logging — all
exercised against the new ``crm.lookup_customer`` / ``billing.create_invoice_draft``
tools. Runs SQLite-backed via the shared fixtures; no Postgres or network.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(settings):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _auth(settings, role: str) -> dict:
    from auth import DevTokenSigner

    signer = DevTokenSigner(secret=settings.dev_token_signing_secret,
                            audience=settings.entra_audience)
    token = signer.mint(subject=f"u-{role}", agent_id=f"a-{role}", role=role)
    return {"Authorization": f"Bearer {token}"}


# --- health checks -------------------------------------------------------
def test_health_liveness(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_health_ai_reports_services_and_tool_surface(client):
    r = client.get("/health/ai")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["services"]) >= {"auth_mode", "queue_backend", "databricks_mode"}

    by_name = {t["name"]: t for t in body["tools"]["registry"]}
    assert "crm.lookup_customer" in by_name
    assert "billing.create_invoice_draft" in by_name
    # the destructive tool is disabled in demo and surfaced as such
    assert by_name["execute_crm_update"]["enabled"] is False
    # the draft tool advertises that it needs approval
    assert by_name["billing.create_invoice_draft"]["requires_approval"] is True
    assert body["tools"]["total"] == len(by_name)
    assert body["tools"]["disabled"] >= 1


# --- RBAC allow / deny on the demo tools ---------------------------------
def test_crm_lookup_allowed_for_sales_and_redacts_pii(client, settings):
    r = client.post("/tools/crm.lookup_customer/invoke",
                    json={"arguments": {"customer_id": "CUST-700"}},
                    headers=_auth(settings, "sales_agent"))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "executed"
    assert body["result"]["name"] == "Helvetia Logistics AG"   # non-sensitive kept
    assert body["result"]["email"] == "***REDACTED***"          # PII masked
    assert body["redaction"]["status"] == "redacted"


def test_crm_lookup_denied_for_finance(client, settings):
    r = client.post("/tools/crm.lookup_customer/invoke",
                    json={"arguments": {"customer_id": "CUST-700"}},
                    headers=_auth(settings, "finance_agent"))
    assert r.status_code == 403
    assert r.json()["decision"] == "denied"
    assert r.json()["error_code"] == "role_not_permitted"


# --- approval gate on the draft tool -------------------------------------
def test_invoice_draft_requires_approval_and_writes_nothing(client, settings):
    r = client.post("/tools/billing.create_invoice_draft/invoke",
                    json={"arguments": {"customer_id": "CUST-700", "amount": 2500,
                                        "currency": "EUR", "description": "Q2 services"}},
                    headers=_auth(settings, "finance_agent"))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "dry_run"
    assert body["result"]["writes_applied"] is False
    assert body["result"]["human_approval_required"] is True
    assert body["approval_id"] and body["approval_id"].startswith("apr_")
    assert body["result"]["draft_id"] == "DRAFT-CUST-700-2500-EUR"  # deterministic


def test_invoice_draft_denied_for_sales(client, settings):
    r = client.post("/tools/billing.create_invoice_draft/invoke",
                    json={"arguments": {"customer_id": "CUST-700", "amount": 100}},
                    headers=_auth(settings, "sales_agent"))
    assert r.status_code == 403
    assert r.json()["error_code"] == "role_not_permitted"


def test_pending_approval_can_be_approved_by_admin(client, settings):
    draft = client.post("/tools/billing.create_invoice_draft/invoke",
                        json={"arguments": {"customer_id": "CUST-701", "amount": 900}},
                        headers=_auth(settings, "finance_agent")).json()
    approval_id = draft["approval_id"]

    # a non-admin cannot approve
    denied = client.post(f"/approvals/{approval_id}/approve",
                         headers=_auth(settings, "finance_agent"))
    assert denied.status_code == 403

    approved = client.post(f"/approvals/{approval_id}/approve",
                           headers=_auth(settings, "admin_agent"))
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


# --- audit logging -------------------------------------------------------
def test_every_decision_is_audited(client, settings):
    client.post("/tools/crm.lookup_customer/invoke",
                json={"arguments": {"customer_id": "CUST-700"}},
                headers=_auth(settings, "sales_agent"))
    client.post("/tools/crm.lookup_customer/invoke",
                json={"arguments": {"customer_id": "CUST-700"}},
                headers=_auth(settings, "finance_agent"))  # denied

    from audit import AuditRepository, session_scope

    with session_scope(settings.database_url) as s:
        calls = AuditRepository(s).recent_tool_calls()
    decisions = {(c.tool_name, c.decision) for c in calls}
    assert ("crm.lookup_customer", "executed") in decisions
    assert ("crm.lookup_customer", "denied") in decisions
