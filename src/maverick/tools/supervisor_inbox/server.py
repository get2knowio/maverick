"""Supervisor inbox MCP tool server.

Generic MCP server that exposes a filtered set of tools per agent.
Each tool represents a message type the supervisor's inbox accepts.
The agent calls these tools to deliver structured messages; the MCP
protocol enforces the parameter schemas.

The --tools flag controls which tools each agent can see.
The --output flag specifies where to write received messages.

Usage:
    python -m maverick.tools.supervisor_inbox.server \\
        --tools submit_outline,submit_details,submit_fix \\
        --output /path/to/inbox.json

The server writes each tool call to the output file as:
    {"tool": "submit_outline", "arguments": {...}}

The supervisor reads this file after each agent turn.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

# Module-level state set at startup
_active_tools: dict[str, Tool] = {}
_output_path: Path = Path("/tmp/mcp-inbox.json")

server = Server("supervisor-inbox")


def _build_mcp_tools(tool_names: set[str]) -> dict[str, Tool]:
    """Build MCP Tool objects from the schema registry."""
    tools: dict[str, Tool] = {}
    for name in tool_names:
        schema = ALL_TOOL_SCHEMAS.get(name)
        if schema is None:
            print(f"WARNING: unknown tool '{name}', skipping", file=sys.stderr)
            continue
        tools[name] = Tool(
            name=schema["name"],
            description=schema["description"],
            inputSchema=schema["inputSchema"],
        )
    return tools


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the tools this agent is allowed to call."""
    return list(_active_tools.values())


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Handle a tool call — write to the inbox file for the supervisor."""
    if name not in _active_tools:
        raise ValueError(
            f"Tool '{name}' is not available. "
            f"Available tools: {', '.join(sorted(_active_tools))}"
        )

    # Write to shared file — the supervisor reads this after the turn
    message = {"tool": name, "arguments": arguments or {}}
    _output_path.parent.mkdir(parents=True, exist_ok=True)
    _output_path.write_text(
        json.dumps(message, indent=2, default=str),
        encoding="utf-8",
    )

    return [TextContent(type="text", text=f"Submitted {name} to supervisor.")]


async def run_server() -> None:
    """Start the MCP server on stdio."""
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point — parse args and start server."""
    global _active_tools, _output_path

    parser = argparse.ArgumentParser(
        description="Supervisor inbox MCP tool server"
    )
    parser.add_argument(
        "--tools",
        required=True,
        help="Comma-separated tool names to expose to this agent",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write inbox messages (JSON file)",
    )
    args = parser.parse_args()

    requested = {t.strip() for t in args.tools.split(",") if t.strip()}
    _active_tools = _build_mcp_tools(requested)
    _output_path = Path(args.output)

    if not _active_tools:
        print(
            f"ERROR: no valid tools found in '{args.tools}'. "
            f"Available: {', '.join(sorted(ALL_TOOL_SCHEMAS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
