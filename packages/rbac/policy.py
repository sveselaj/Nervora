"""The RBAC decision function.

Decisions are deny-by-default: a role must be explicitly listed in a tool's
``required_roles`` to be allowed. The admin role is *not* implicitly granted
everything — admin is listed explicitly on the tools it may call, so the
policy matrix stays auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DecisionReason(StrEnum):
    ALLOWED = "allowed"
    ROLE_NOT_PERMITTED = "role_not_permitted"
    UNKNOWN_ROLE = "unknown_role"
    TOOL_DISABLED = "tool_disabled"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: DecisionReason
    detail: str = ""

    @property
    def code(self) -> str:
        return self.reason.value


def evaluate(*, role: str, required_roles: tuple[str, ...], known_roles: set[str],
             tool_enabled: bool = True) -> Decision:
    """Return whether ``role`` may invoke a tool requiring ``required_roles``."""
    if role not in known_roles:
        return Decision(False, DecisionReason.UNKNOWN_ROLE, f"role '{role}' is not recognised")
    if not tool_enabled:
        return Decision(False, DecisionReason.TOOL_DISABLED, "tool is disabled in this environment")
    if role in required_roles:
        return Decision(True, DecisionReason.ALLOWED)
    return Decision(
        False,
        DecisionReason.ROLE_NOT_PERMITTED,
        f"role '{role}' is not permitted; requires one of {sorted(required_roles)}",
    )
