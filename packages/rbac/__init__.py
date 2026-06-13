"""Tool-level role-based access control.

RBAC here is intentionally simple and *explicit*: every tool declares the set
of roles allowed to call it (see ``tool_registry``), and :func:`evaluate`
returns an allow/deny :class:`Decision` plus a machine-readable reason. The
gateway must call :func:`evaluate` BEFORE any tool side effect, and must log
denials.
"""

from rbac.policy import Decision, DecisionReason, evaluate
from rbac.roles import AgentRole, all_roles

__all__ = ["AgentRole", "all_roles", "Decision", "DecisionReason", "evaluate"]
