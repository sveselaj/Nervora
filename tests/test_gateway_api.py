"""End-to-end HTTP tests through the FastAPI app with real dev tokens."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(settings):
    # Import after settings env is in place so the app boots against SQLite.
    from app.main import app

    with TestClient(app) as c:
        yield c


def _token(settings, role: str) -> str:
    from auth import DevTokenSigner

    signer = DevTokenSigner(secret=settings.dev_token_signing_secret,
                            audience=settings.entra_audience)
    return signer.mint(subject=f"u-{role}", agent_id=f"a-{role}", role=role)


def _auth(settings, role: str) -> dict:
    return {"Authorization": f"Bearer {_token(settings, role)}"}


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_tools_listed(client):
    r = client.get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    assert "trigger_databricks_workflow" in names and len(names) >= 7


def test_missing_token_is_401(client):
    r = client.post("/tools/get_invoice_status/invoke", json={"arguments": {"invoice_id": "INV-5001"}})
    assert r.status_code == 401


def test_finance_allowed_invoice(client, settings):
    r = client.post("/tools/get_invoice_status/invoke",
                    json={"arguments": {"invoice_id": "INV-5001"}},
                    headers=_auth(settings, "finance_agent"))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "executed"
    assert body["result"]["status"] == "paid"
    assert r.headers.get("X-Trace-Id")  # trace id echoed in response header
    assert body["trace_id"]


def test_sales_denied_hr_returns_403(client, settings):
    r = client.post("/tools/get_employee_profile/invoke",
                    json={"arguments": {"employee_id": "E-1001"}},
                    headers=_auth(settings, "sales_agent"))
    assert r.status_code == 403
    assert r.json()["decision"] == "denied"


def test_async_returns_202_and_job_id(client, settings):
    r = client.post("/tools/trigger_databricks_workflow/invoke",
                    json={"arguments": {"workflow_name": "wf", "parameters": {}}},
                    headers={**_auth(settings, "finance_agent"), "Idempotency-Key": "http-k1"})
    assert r.status_code == 202
    assert r.json()["decision"] == "queued" and r.json()["job_id"]


def test_destructive_blocked_403(client, settings):
    r = client.post("/tools/execute_crm_update/invoke",
                    json={"arguments": {"account_id": "ACC-300", "approved_change_id": "x"}},
                    headers={**_auth(settings, "admin_agent"), "X-Approval-Token": "x"})
    assert r.status_code == 403
    assert r.json()["error_code"] == "tool_disabled"


def test_invalid_token_rejected(client):
    r = client.post("/tools/get_invoice_status/invoke",
                    json={"arguments": {"invoice_id": "INV-5001"}},
                    headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401
