#!/usr/bin/env python
"""Inspect ACP session config options advertised by an ACP agent.

Usage:
  uv run python scripts/inspect_acp_config.py              # claude-agent-acp (default)
  uv run python scripts/inspect_acp_config.py copilot      # copilot --acp --stdio
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import os
import sys

from acp import PROTOCOL_VERSION, spawn_agent_process
from acp.schema import ClientCapabilities, Implementation

AGENTS = {
    "claude": ("claude-agent-acp",),
    "copilot": ("copilot", "--acp", "--stdio"),
}


class InspectorClient:
    async def session_update(self, session_id, update, **kwargs):  # noqa: ANN001, ANN003
        pass

    async def request_permission(self, options, session_id, tool_call, **kwargs):  # noqa: ANN001, ANN003
        from acp.schema import AllowedOutcome, RequestPermissionResponse
        return RequestPermissionResponse(
            outcome=AllowedOutcome(option_id="", outcome="selected")
        )


def print_config_options(config_options):
    """Print config options with full detail."""
    print(f"\n=== Config Options ({len(config_options)}) ===", flush=True)
    for opt in config_options:
        root = getattr(opt, "root", opt)
        print(f"\n  ID:            {getattr(root, 'id', '?')}", flush=True)
        print(f"  Name:          {getattr(root, 'name', '?')}", flush=True)
        print(f"  Current Value: {getattr(root, 'current_value', '?')}", flush=True)
        print(f"  Category:      {getattr(root, 'category', None)}", flush=True)
        print(f"  Description:   {getattr(root, 'description', None)}", flush=True)
        options = getattr(root, "options", [])
        if options:
            print("  Options:", flush=True)
            for o in options:
                if hasattr(o, "options"):
                    # SessionConfigSelectGroup
                    print(f"    Group: {getattr(o, 'label', '?')}", flush=True)
                    for sub in o.options:
                        desc = getattr(sub, "description", "")
                        desc_str = f" — {desc}" if desc else ""
                        print(f"      - {getattr(sub, 'value', getattr(sub, 'id', '?'))}: "
                              f"{getattr(sub, 'name', '?')}{desc_str}", flush=True)
                else:
                    desc = getattr(o, "description", "")
                    desc_str = f" — {desc}" if desc else ""
                    print(f"    - {getattr(o, 'value', getattr(o, 'id', '?'))}: "
                          f"{getattr(o, 'name', '?')}{desc_str}", flush=True)


async def main() -> None:
    agent_key = sys.argv[1] if len(sys.argv) > 1 else "claude"
    if agent_key not in AGENTS:
        print(f"Unknown agent: {agent_key}. Choose from: {list(AGENTS.keys())}")
        sys.exit(1)

    cmd_args = AGENTS[agent_key]
    command, *args = cmd_args

    client_info = Implementation(
        name="maverick-inspector",
        version=importlib.metadata.version("maverick-cli"),
    )
    client = InspectorClient()

    env = {**os.environ}
    for key in list(env):
        if "CLAUDE" in key.upper():
            env.pop(key)

    print(f"Spawning: {' '.join(cmd_args)}", flush=True)
    ctx = spawn_agent_process(client, command, *args, env=env)
    conn, proc = await ctx.__aenter__()
    print(f"Subprocess PID: {proc.pid}\n", flush=True)

    # Drain early stderr
    async def drain_stderr():
        if proc.stderr:
            try:
                data = await asyncio.wait_for(proc.stderr.read(4096), timeout=3.0)
                if data:
                    print(f"stderr: {data.decode()}", flush=True)
            except (TimeoutError, Exception):
                pass

    await drain_stderr()

    print("Initializing ACP connection...", flush=True)
    try:
        init_resp = await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=client_info,
            ),
            timeout=15.0,
        )
        ai = init_resp.agent_info
        if ai:
            print(f"Agent: {ai.name} v{ai.version}", flush=True)
        print(f"Capabilities: {init_resp.agent_capabilities}", flush=True)
    except TimeoutError:
        print("ERROR: initialize() timed out after 15s", flush=True)
        await drain_stderr()
        proc.kill()
        return

    print("\nCreating new session...", flush=True)
    try:
        session = await asyncio.wait_for(
            conn.new_session(cwd=os.getcwd(), mcp_servers=[]),
            timeout=15.0,
        )
    except TimeoutError:
        print("ERROR: new_session() timed out after 15s", flush=True)
        await drain_stderr()
        proc.kill()
        return
    except Exception as exc:
        print(f"ERROR: new_session() failed: {exc}", flush=True)
        await drain_stderr()
        proc.kill()
        return

    print(f"Session ID: {session.session_id}", flush=True)

    # --- Config Options ---
    config_options = getattr(session, "config_options", None)
    if config_options:
        print_config_options(config_options)
    else:
        print("\nNo config_options returned by new_session()", flush=True)

    # --- Modes ---
    modes = getattr(session, "modes", None)
    if modes:
        print("\n=== Modes ===", flush=True)
        print(f"  Current: {getattr(modes, 'current_mode_id', '?')}", flush=True)
        for m in getattr(modes, "modes", []):
            desc = getattr(m, "description", "")
            desc_str = f" — {desc}" if desc else ""
            print(f"  - {getattr(m, 'id', '?')}: {getattr(m, 'name', '?')}{desc_str}",
                  flush=True)
    else:
        print("\nNo modes returned", flush=True)

    # --- Models ---
    models = getattr(session, "models", None)
    if models:
        print("\n=== Models ===", flush=True)
        print(f"  Current: {getattr(models, 'current_model_id', '?')}", flush=True)
        for m in getattr(models, "available_models", []):
            desc = getattr(m, "description", "")
            desc_str = f" — {desc}" if desc else ""
            print(f"  - {getattr(m, 'model_id', '?')}: {getattr(m, 'name', '?')}{desc_str}",
                  flush=True)
    else:
        print("\nNo models returned", flush=True)

    # Cleanup: cancel session, close connection, wait for subprocess exit
    try:
        await asyncio.wait_for(conn.cancel(session_id=session.session_id), timeout=3.0)
    except Exception:
        pass
    try:
        await asyncio.wait_for(ctx.__aexit__(None, None, None), timeout=3.0)
    except Exception:
        pass
    # Ensure subprocess is fully terminated before the event loop closes,
    # otherwise BaseSubprocessTransport.__del__ raises RuntimeError.
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=3.0)
    except Exception:
        proc.kill()

    print("\nDone.", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
