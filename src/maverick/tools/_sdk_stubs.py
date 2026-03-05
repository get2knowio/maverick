"""Typed stubs for claude_agent_sdk symbols used by legacy modules.

These stubs are used when claude_agent_sdk is not installed (ACP migration T051).
They allow modules to be imported without errors while providing enough
type information for mypy strict mode. The stubs replicate the runtime behaviour
of the real SDK objects so that existing tests continue to pass.

Usage:
    try:
        from claude_agent_sdk import create_sdk_mcp_server, tool
        from claude_agent_sdk.types import McpSdkServerConfig
    except ImportError:
        from maverick.tools._sdk_stubs import (
            McpSdkServerConfig, create_sdk_mcp_server, tool
        )

    try:
        from claude_agent_sdk import ClaudeAgentOptions
    except ImportError:
        from maverick.tools._sdk_stubs import ClaudeAgentOptions
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass
class ClaudeAgentOptions:
    """Stub for ClaudeAgentOptions when claude_agent_sdk is not installed.

    Replicates the constructor signature used by existing code so that
    tests can instantiate it and mock the downstream ``query`` call.
    """

    system_prompt: str = ""
    model: str = "claude-3-haiku-20240307"
    max_turns: int = 1
    allowed_tools: list[str] = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 1.0


class _ToolWrapper:
    """Wraps a decorated tool function and exposes SDK-compatible attributes.

    The real claude_agent_sdk @tool decorator wraps the function in an object
    with the following attributes used by tests and server introspection:

    - ``.handler``: the original async callable (called by tests directly)
    - ``.name``: the tool name string passed to @tool(name, ...)
    - ``.description``: the description string passed to @tool(..., description, ...)
    - ``.input_schema``: the schema dict passed to @tool(..., ..., schema)
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self.handler: Callable[..., Any] = fn
        self.name: str = name
        self.description: str = description
        self.input_schema: dict[str, Any] = input_schema
        # Preserve function metadata for introspection
        functools.update_wrapper(self, fn)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.handler(*args, **kwargs)


def tool(
    name: str,
    description: str,
    schema: dict[str, Any],
) -> Callable[[_F], _ToolWrapper]:
    """No-op decorator stub for @tool when SDK is not installed.

    Returns a decorator that wraps the function in a _ToolWrapper so that
    ``decorated_fn.handler(args)`` works the same as with the real SDK, and
    ``decorated_fn.name`` / ``decorated_fn.input_schema`` are available for
    tests and server introspection.
    """
    _name = name
    _description = description
    _schema = schema

    def _decorator(f: _F) -> _ToolWrapper:
        return _ToolWrapper(
            f, name=_name, description=_description, input_schema=_schema
        )

    return _decorator


def create_sdk_mcp_server(
    name: str,
    version: str,
    tools: list[Any],
) -> dict[str, Any]:
    """No-op server factory stub when SDK is not installed.

    Returns a dict matching the real SDK's McpSdkServerConfig TypedDict shape
    so that tests checking server["name"], server["instance"], server["type"]
    continue to pass.
    """
    return {
        "name": name,
        "version": version,
        "type": "sdk",
        "instance": None,  # No real MCP server instance when SDK is absent
        "tools": tools,
    }


#: Stub for McpSdkServerConfig TypedDict — use plain dict at runtime.
McpSdkServerConfig = dict
