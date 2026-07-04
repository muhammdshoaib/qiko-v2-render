"""Thin adapter that surfaces the platform ToolRegistry over the Python MCP SDK.

The registry (tools.py) holds the validated tools and handlers; this wrapper only wires them to
an MCP server. The SDK import and the running server are integration concerns, not unit-tested.
"""
from __future__ import annotations

from app.modules.agentcore.tools import ToolRegistry


def create_mcp_server(registry: ToolRegistry, *, name: str = "qiko-core"):  # pragma: no cover - requires mcp SDK + runtime
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)
    for tool_name in registry.names():
        tool = registry._tools[tool_name]  # noqa: SLF001 - internal wiring

        def _make(handler, schema):
            def _call(**kwargs):
                return handler(schema(**kwargs))
            return _call

        server.add_tool(_make(tool.handler, tool.schema), name=tool_name)
    return server
