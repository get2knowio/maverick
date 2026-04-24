"""Supervisor inbox MCP tool server.

Generic MCP server that exposes a filtered set of tools per agent. Each
tool represents a structured result the AGENT owns. Tool calls flow:

    agent → MCP stdio → this server → agent_actor.on_tool_call(...)

During the Thespian→xoscar migration, this server supports two
discovery modes — set by ``serve_inbox`` at startup via module globals:

* **xoscar (preferred):** ``_inbox_ref`` is a live ``xo.ActorRef``
  pointing at the agent actor whose inbox we serve. Tool calls invoke
  ``await _inbox_ref.on_tool_call(name, args)``.
* **Thespian (legacy):** ``_thespian_system`` / ``_thespian_inbox`` are
  the ActorSystem + supervisor address resolved by globalName. Tool
  calls are delivered via ``tell()``.

The directory name ``supervisor_inbox/`` is a Thespian-era misnomer
once agents own their inboxes. Phase 4 renames the package to
``agent_inbox/``; no rename during Phase 1 to minimise churn.
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

# Module-level state set at startup by the serve_inbox command.
_active_tools: dict[str, Tool] = {}

# xoscar mode (preferred post-migration).
_inbox_ref: Any = None

# Thespian mode (legacy, kept until Phase 4).
_thespian_system: Any = None
_thespian_inbox: Any = None

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
    print(
        f"INBOX_SERVER: list_tools called, returning: {list(_active_tools.keys())}",
        file=sys.stderr,
        flush=True,
    )
    return list(_active_tools.values())


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Handle a tool call — validate and deliver to the configured inbox."""
    if name not in _active_tools:
        raise ValueError(
            f"Tool '{name}' is not available. Available tools: {', '.join(sorted(_active_tools))}"
        )

    args = arguments or {}

    # Validate arguments against the tool's JSON Schema.
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

    print(
        f"INBOX_SERVER: tool call received: {name} "
        f"(args keys: {list(args.keys()) if args else 'none'})",
        file=sys.stderr,
        flush=True,
    )

    if _inbox_ref is not None:
        # xoscar: typed in-pool RPC to the agent actor's on_tool_call.
        result = await _inbox_ref.on_tool_call(name, args)
        print(
            f"INBOX_SERVER: delivered {name} to agent (xoscar) — result={result!r}",
            file=sys.stderr,
            flush=True,
        )
        return [
            TextContent(
                type="text",
                text=f"Submitted {name} to agent (result: {result}).",
            )
        ]

    if _thespian_system is not None and _thespian_inbox is not None:
        # Legacy Thespian: one-way tell().
        message = {"tool": name, "arguments": args}
        _thespian_system.tell(_thespian_inbox, message)
        print(
            f"INBOX_SERVER: delivered {name} to supervisor (thespian)",
            file=sys.stderr,
            flush=True,
        )
        return [TextContent(type="text", text=f"Submitted {name} to supervisor.")]

    print(
        f"WARNING: no inbox configured, message dropped: {name}",
        file=sys.stderr,
    )
    return [
        TextContent(
            type="text",
            text=f"WARNING: {name} dropped — no inbox configured on this server.",
        )
    ]


async def run_server() -> None:
    """Start the MCP server on stdio."""
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )
