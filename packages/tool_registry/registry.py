"""The in-memory tool registry."""

from __future__ import annotations

from tool_registry.spec import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool registration: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


def build_default_registry(*, demo_mode: bool = True) -> ToolRegistry:
    """Build the registry with the seven reference tools.

    ``demo_mode`` flips the destructive ``execute_crm_update`` tool off so it is
    hard-denied regardless of role/approval — the safe default for a public
    reference deployment.
    """
    from tool_registry import tools

    return tools.build_registry(demo_mode=demo_mode)
