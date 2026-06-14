"""The published tool registry.

Every tool the gateway can execute is declared here with its full policy
metadata (name, description, required roles, read/write/destructive class,
sync/async mode, PII class, dry-run requirement). The registry is the *only*
source of callable tools — there are no hidden tools, which is one of the
gateway's stated guarantees. ``crm.lookup_customer`` and
``billing.create_invoice_draft`` are the Phase 1 demo-flow tools.
"""

from tool_registry.registry import ToolRegistry, build_default_registry
from tool_registry.spec import (
    Classification,
    ExecutionMode,
    PIIClass,
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
)

__all__ = [
    "ToolRegistry",
    "build_default_registry",
    "ToolSpec",
    "ToolContext",
    "ToolResult",
    "ToolError",
    "Classification",
    "ExecutionMode",
    "PIIClass",
]
