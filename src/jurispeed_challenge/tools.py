from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from jurispeed_challenge.types import ToolSchema


ToolHandler = Callable[[dict[str, Any]], Any]


class ToolExecutionError(RuntimeError):
    """Se lanza cuando una herramienta local no puede ejecutarse."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> ToolSchema:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def schemas(self) -> list[ToolSchema]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolExecutionError(f"Herramienta solicitada desconocida: {tool_name}")
        return tool.handler(tool_input)


def tool_result_to_text(result: Any) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
