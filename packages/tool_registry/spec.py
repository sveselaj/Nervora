"""Tool specification types.

A :class:`ToolSpec` is a declarative policy object plus a ``run`` callable. The
gateway reads the declarative half to make auth/RBAC/PII/async decisions and
only invokes ``run`` once those checks pass (and, for async tools, only inside
the worker).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Classification(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ExecutionMode(StrEnum):
    SYNC = "sync"
    ASYNC = "async"


class PIIClass(StrEnum):
    NONE = "none"
    LOW = "low"
    SENSITIVE = "sensitive"


class ToolError(Exception):
    """Raised by a tool handler. ``code`` is recorded in the audit trail."""

    def __init__(self, message: str, code: str = "TOOL_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ToolContext:
    """Dependencies a tool handler may use. Injected by gateway/worker."""

    settings: Any
    databricks: Any  # databricks_connector.DatabricksConnector


@dataclass
class ToolResult:
    """The output of a tool's ``run``. ``output`` is the model-visible payload
    (after the gateway applies redaction)."""

    output: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    required_roles: tuple[str, ...]
    classification: Classification
    execution_mode: ExecutionMode
    pii_classification: PIIClass
    dry_run_required: bool
    input_model: type[BaseModel]
    run: Callable[[ToolContext, dict[str, Any]], ToolResult]
    # Keys in the output that must be masked before becoming model-visible,
    # unless policy + role explicitly permit raw access.
    sensitive_fields: frozenset[str] = field(default_factory=frozenset)
    # Roles permitted to see raw (un-redacted) PII for this tool.
    raw_pii_roles: tuple[str, ...] = field(default_factory=tuple)
    # Hard kill-switch: a disabled tool is denied regardless of role.
    enabled: bool = True
    # Destructive tools require this approval token to even be considered.
    requires_approval_token: bool = False

    def validate_args(self, args: dict[str, Any]) -> dict[str, Any]:
        model = self.input_model(**args)
        return model.model_dump()

    def policy_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_roles": list(self.required_roles),
            "classification": self.classification.value,
            "execution_mode": self.execution_mode.value,
            "pii_classification": self.pii_classification.value,
            "dry_run_required": self.dry_run_required,
            "enabled": self.enabled,
            "requires_approval_token": self.requires_approval_token,
        }
