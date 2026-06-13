"""Agent roles recognised by the gateway.

These map to Entra ID app roles / group claims in production. The demo uses
four agent personas plus an admin."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    HR_AGENT = "hr_agent"
    FINANCE_AGENT = "finance_agent"
    SALES_AGENT = "sales_agent"
    ADMIN_AGENT = "admin_agent"


def all_roles() -> list[str]:
    return [r.value for r in AgentRole]
