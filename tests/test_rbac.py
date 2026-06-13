"""RBAC policy + gateway enforcement."""

from rbac import all_roles, evaluate


def test_allowed_when_role_matches():
    d = evaluate(role="finance_agent", required_roles=("finance_agent", "admin_agent"),
                 known_roles=set(all_roles()))
    assert d.allowed and d.code == "allowed"


def test_denied_when_role_not_permitted():
    d = evaluate(role="sales_agent", required_roles=("hr_agent", "admin_agent"),
                 known_roles=set(all_roles()))
    assert not d.allowed and d.code == "role_not_permitted"


def test_unknown_role_denied():
    d = evaluate(role="ghost_agent", required_roles=("admin_agent",),
                 known_roles=set(all_roles()))
    assert not d.allowed and d.code == "unknown_role"


def test_disabled_tool_denied_even_for_required_role():
    d = evaluate(role="admin_agent", required_roles=("admin_agent",),
                 known_roles=set(all_roles()), tool_enabled=False)
    assert not d.allowed and d.code == "tool_disabled"


def test_admin_not_implicitly_granted_everything():
    # admin must be explicitly listed; it is NOT a wildcard.
    d = evaluate(role="admin_agent", required_roles=("finance_agent",),
                 known_roles=set(all_roles()))
    assert not d.allowed


def test_gateway_denies_cross_domain_and_logs(executor, principal_factory):
    sales = principal_factory("sales_agent")
    out = executor.invoke(principal=sales, tool_name="get_employee_profile",
                          arguments={"employee_id": "E-1001"})
    assert out.decision == "denied"
    assert out.error_code == "role_not_permitted"

    # the denial must be in the audit trail
    from audit import AuditRepository, session_scope

    with session_scope(executor.settings.database_url) as s:
        calls = AuditRepository(s).recent_tool_calls()
    assert any(c.decision == "denied" and c.tool_name == "get_employee_profile" for c in calls)
