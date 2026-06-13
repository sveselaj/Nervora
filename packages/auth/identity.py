"""The authenticated caller identity used throughout the gateway."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """A verified caller.

    ``subject`` is the OIDC ``sub`` (the human/service principal). ``agent_id``
    identifies the *AI agent* acting on the caller's behalf, and ``role`` is the
    single agent role used for tool-level RBAC. Keeping the agent identity
    distinct from the human subject is what lets us audit "which agent did what
    on whose authority".
    """

    subject: str
    agent_id: str
    role: str
    scopes: tuple[str, ...] = field(default_factory=tuple)
    tenant_id: str = ""
    raw_claims: dict = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
