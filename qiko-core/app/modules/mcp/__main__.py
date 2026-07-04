"""Run the Qiko MCP server over stdio:  python -m app.modules.mcp

Surfaces the knowledge tool registry over the Python MCP SDK so external MCP clients can call the
platform's tools. Requires the `mcp` SDK; this is a runtime entrypoint, not unit-tested.
"""
from __future__ import annotations

from app.modules.knowledge.service import KnowledgeService
from app.modules.mcp.server import create_mcp_server
from app.modules.mcp.tools import build_registry


def main() -> None:  # pragma: no cover - requires the mcp SDK + runtime
    registry = build_registry(KnowledgeService(), tenant="default")
    create_mcp_server(registry).run()


if __name__ == "__main__":  # pragma: no cover
    main()
