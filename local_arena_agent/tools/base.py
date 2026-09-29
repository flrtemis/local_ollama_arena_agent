from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    function: ToolFn
    requires_approval: bool = False
    category: str = "general"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "requires_approval": t.requires_approval,
                "category": t.category,
            }
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: {name}", "blocked": True}
        try:
            return tool.function(arguments)
        except Exception as e:
            return {"ok": False, "error": repr(e), "tool": name}
