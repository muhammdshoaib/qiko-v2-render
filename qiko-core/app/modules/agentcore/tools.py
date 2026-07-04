"""Tool orchestration. Tools are registered with a Pydantic input schema; arguments are validated
before the tool runs, and tool output is treated as untrusted (LLM01/05 guardrails). This is the
in-process registry; exposure over the Python MCP SDK is delivered in SCRUM-13.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError


class ToolError(Exception):
    pass


@dataclass
class Tool:
    name: str
    schema: type[BaseModel]
    handler: Callable[[BaseModel], object]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, schema: type[BaseModel]) -> Callable:
        def wrap(handler: Callable[[BaseModel], object]) -> Callable:
            self._tools[name] = Tool(name=name, schema=schema, handler=handler)
            return handler
        return wrap

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def invoke(self, name: str, args: dict) -> object:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        try:
            validated = tool.schema(**args)
        except ValidationError as e:
            raise ToolError(f"invalid arguments for {name}: {e.error_count()} error(s)") from e
        result = tool.handler(validated)  # handlers may be sync or async
        return await result if inspect.isawaitable(result) else result
