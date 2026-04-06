"""Supervisor inbox MCP tool server.

Generic MCP server that exposes a filtered set of tools per agent.
Each tool represents a message type the supervisor's inbox accepts.
The agent calls these tools to deliver structured messages; the MCP
protocol provides schema guidance, and we enforce it server-side
via jsonschema validation.

Tool call data is delivered to the supervisor's Thespian inbox actor
via message passing — no filesystem coordination.

Usage (called by agent subprocess, not manually):
    maverick serve-inbox --tools submit_outline,submit_details,submit_fix
"""

from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

# Module-level state set at startup by serve_inbox command
_active_tools: dict[str, Tool] = {}
_thespian_system: Any = None  # ActorSystem
_thespian_inbox: Any = None   # ActorAddress

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
    """Handle a tool call — validate and deliver to supervisor inbox."""
    if name not in _active_tools:
        raise ValueError(
            f"Tool '{name}' is not available. "
            f"Available tools: {', '.join(sorted(_active_tools))}"
        )

    args = arguments or {}

    # Validate arguments against the tool's input schema
    tool_def = _active_tools[name]
    schema = tool_def.inputSchema
    if schema:
        import jsonschema

        try:
            jsonschema.validate(instance=args, schema=schema)
        except jsonschema.ValidationError as exc:
            error_path = (
                " → ".join(str(p) for p in exc.absolute_path)
                if exc.absolute_path
                else "(root)"
            )
            raise ValueError(
                f"Schema validation failed for '{name}' at '{error_path}': "
                f"{exc.message}. Please fix the arguments and call "
                f"'{name}' again."
            ) from exc

    # Deliver to supervisor's Thespian inbox actor
    message = {"tool": name, "arguments": args}

    if _thespian_system is not None and _thespian_inbox is not None:
        _thespian_system.tell(_thespian_inbox, message)
    else:
        # Fallback: log warning (shouldn't happen in normal operation)
        print(
            f"WARNING: no Thespian inbox configured, message dropped: {name}",
            file=sys.stderr,
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
