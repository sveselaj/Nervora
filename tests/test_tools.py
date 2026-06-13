"""Tool registry + sync/dry-run/destructive execution semantics."""


from tool_registry import build_default_registry


def test_registry_has_at_least_seven_tools():
    reg = build_default_registry(demo_mode=True)
    assert len(reg) >= 7
    expected = {
        "get_employee_profile", "check_leave_balance", "get_invoice_status",
        "run_budget_variance_report", "trigger_databricks_workflow",
        "create_crm_update_dry_run", "execute_crm_update",
    }
    assert expected.issubset(set(reg.names()))


def test_destructive_tool_disabled_in_demo():
    reg = build_default_registry(demo_mode=True)
    assert reg.get("execute_crm_update").enabled is False
    reg_prod = build_default_registry(demo_mode=False)
    assert reg_prod.get("execute_crm_update").enabled is True


def test_employee_profile_redacted_by_default(executor, principal_factory):
    hr = principal_factory("hr_agent")
    out = executor.invoke(principal=hr, tool_name="get_employee_profile",
                          arguments={"employee_id": "E-1001"})
    assert out.decision == "executed"
    assert out.result["salary"] == "***REDACTED***"
    assert out.result["national_id"] == "***REDACTED***"
    assert out.result["name"] == "Anika Brandt"  # non-sensitive preserved
    assert out.redaction_status == "redacted"


def test_budget_variance_reads_mock_databricks(executor, principal_factory):
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="run_budget_variance_report",
                          arguments={"department_id": "FIN-100", "period": "2024-Q2"})
    assert out.decision == "executed"
    assert out.result["total_budget"] > 0
    assert out.result["line_items"]
    assert out.result["statement_id"].startswith("stmt_")


def test_dry_run_never_writes_and_requires_approval(executor, principal_factory):
    sales = principal_factory("sales_agent")
    out = executor.invoke(principal=sales, tool_name="create_crm_update_dry_run",
                          arguments={"account_id": "ACC-300",
                                     "proposed_changes": {"tier": "gold"}})
    assert out.decision == "dry_run"
    assert out.result["writes_applied"] is False
    assert out.result["human_approval_required"] is True
    assert out.approval_id and out.approval_id.startswith("apr_")
    assert any(d["field"] == "tier" and d["to"] == "gold" for d in out.result["diff"])


def test_execute_crm_update_blocked_in_demo(executor, principal_factory):
    admin = principal_factory("admin_agent")
    out = executor.invoke(principal=admin, tool_name="execute_crm_update",
                          arguments={"account_id": "ACC-300",
                                     "approved_change_id": "apr_x"},
                          approval_token="anything")
    assert out.decision == "denied"
    # Disabled tools are caught by the RBAC gate first (deny-by-default).
    assert out.error_code == "tool_disabled"


def test_unknown_tool_denied_not_silent(executor, principal_factory):
    admin = principal_factory("admin_agent")
    out = executor.invoke(principal=admin, tool_name="secret_backdoor", arguments={})
    assert out.decision == "denied" and out.error_code == "UNKNOWN_TOOL"


def test_invalid_arguments_rejected(executor, principal_factory):
    fin = principal_factory("finance_agent")
    out = executor.invoke(principal=fin, tool_name="get_invoice_status", arguments={})
    assert out.decision == "failed" and out.error_code == "INVALID_ARGUMENTS"


def test_destructive_execution_when_enabled_requires_approved_record(
    settings, session_factory, principal_factory, monkeypatch
):
    # prod-mode registry (tool enabled) + configured approval token, but no
    # approved record -> still denied.
    monkeypatch.setenv("ADMIN_APPROVAL_TOKEN", "tok-123")
    import common.settings as cs

    cs.get_settings.cache_clear()
    s = cs.get_settings()
    from app.executor import Executor
    from databricks_connector import build_connector
    from servicebus import build_queue

    ex = Executor(
        registry=build_default_registry(demo_mode=False), settings=s,
        queue=build_queue(s), databricks=build_connector(s),
        session_factory=session_factory,
    )
    admin = principal_factory("admin_agent")
    out = ex.invoke(principal=admin, tool_name="execute_crm_update",
                    arguments={"account_id": "ACC-300", "approved_change_id": "apr_missing"},
                    approval_token="tok-123")
    assert out.decision == "denied" and out.error_code == "APPROVAL_NOT_APPROVED"
