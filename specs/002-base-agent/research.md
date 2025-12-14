# Research: Base Agent Abstraction Layer

**Feature**: 002-base-agent | **Date**: 2025-12-12

## Overview

This document captures research findings for building the `MaverickAgent` base class that wraps Claude Agent SDK interactions.

---

## 1. SDK Client Pattern

### Decision: Use `ClaudeSDKClient` for multi-turn agent interactions

### Rationale
`ClaudeSDKClient` provides:
- Multi-turn conversation context (essential for complex agent workflows)
- Custom tools via SDK MCP servers (in-process, no subprocess overhead)
- Hooks for validation and logging (aligns with fail-gracefully principle)
- `interrupt()` for stopping long-running tasks
- Async context manager for clean resource management

### Alternatives Considered
- `query()` function: Too limited - no custom tools, no hooks, no multi-turn context

### Implementation

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=ClaudeAgentOptions(...)) as client:
    await client.query("Analyze this code")
    async for msg in client.receive_response():
        yield msg
```

---

## 2. Streaming Pattern

### Decision: Use `receive_response()` for natural message streaming

### Rationale
- Automatically stops at `ResultMessage` (natural completion boundary)
- Matches the request/response pattern expected by workflows
- Simplifies response aggregation and usage tracking

### Alternatives Considered
- `receive_messages()`: Requires manual stopping logic, more complex for typical agent use cases

### Implementation

```python
async for message in client.receive_response():
    yield message
    # Stops automatically at ResultMessage
```

---

## 3. Error Mapping

### Decision: Map SDK errors to Maverick's error hierarchy (FR-007)

### Rationale
- Hide SDK implementation details (encapsulation)
- Provide actionable error messages
- Align with constitution's fail-gracefully principle

### Mapping Table

| SDK Error | Maverick Error | Additional Context |
|-----------|---------------|-------------------|
| `CLINotFoundError` | `CLINotFoundError` | Include install instructions |
| `ProcessError` | `ProcessError` | Include exit code and stderr |
| `CLIConnectionError` | `NetworkError` | Include connection details |
| `CLIJSONDecodeError` | `MalformedResponseError` | Attach raw response |
| Generic `ClaudeSDKError` | `AgentError` | Wrap with agent name |

### Implementation

```python
def _wrap_sdk_error(self, error: Exception) -> Exception:
    if isinstance(error, CLINotFoundError):
        return MaverickCLINotFoundError(
            "Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code",
            cli_path=getattr(error, "cli_path", None)
        )
    # ... additional mappings
```

---

## 4. Tool Validation

### Decision: Validate `allowed_tools` at construction time (FR-002)

### Rationale
- Fail fast principle: catch configuration errors early
- Prevents runtime failures from typos in tool names
- Standard approach in service registries and DI containers

### Built-in Tools

```python
BUILTIN_TOOLS = {
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite",
    "BashOutput", "KillBash", "Task", "ExitPlanMode",
    "ListMcpResources", "ReadMcpResource"
}
```

### MCP Tool Pattern
MCP tools follow pattern: `mcp__<server>__<tool>` (e.g., `mcp__analysis__analyze_code`)

---

## 5. Custom Tools

### Decision: Use SDK MCP servers (in-process) for custom tools

### Rationale
- No subprocess management overhead
- Better performance (no IPC)
- Simpler deployment (single Python process)
- Easier debugging (all code in same process)

### Alternatives Considered
- External MCP servers (stdio): More complex, subprocess overhead, but necessary for non-Python tools

### Implementation

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("analyze_code", "Analyze code quality", {"file_path": str})
async def analyze_code(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": "Analysis..."}]}

tools_server = create_sdk_mcp_server(
    name="custom-tools",
    version="1.0.0",
    tools=[analyze_code]
)
```

---

## 6. Usage Statistics

### Decision: Extract from `ResultMessage` (FR-014)

### Rationale
`ResultMessage` provides complete execution statistics:
- `duration_ms`: Total execution time
- `total_cost_usd`: API cost (may be None)
- `usage`: Token counts (input_tokens, output_tokens)
- `num_turns`: Conversation turns

### Implementation

```python
@dataclass
class AgentUsage:
    input_tokens: int
    output_tokens: int
    total_cost_usd: float | None
    duration_ms: int

# Extract from ResultMessage
result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
usage = AgentUsage(
    input_tokens=result_msg.usage.get("input_tokens", 0) if result_msg.usage else 0,
    output_tokens=result_msg.usage.get("output_tokens", 0) if result_msg.usage else 0,
    total_cost_usd=result_msg.total_cost_usd,
    duration_ms=result_msg.duration_ms
)
```

---

## 7. Key SDK Types

### Message Types

```python
from claude_agent_sdk import (
    Message,           # Union of all message types
    AssistantMessage,  # Claude's response
    UserMessage,       # User input
    SystemMessage,     # System messages with metadata
    ResultMessage      # Final result with cost/usage
)
```

### Content Blocks

```python
from claude_agent_sdk import (
    TextBlock,         # text: str
    ThinkingBlock,     # thinking: str (extended thinking)
    ToolUseBlock,      # id, name, input
    ToolResultBlock    # tool_use_id, content, is_error
)
```

### Configuration

```python
from claude_agent_sdk import ClaudeAgentOptions

ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit"],
    system_prompt="You are...",
    model="claude-sonnet-4-5-20250929",
    permission_mode="acceptEdits",
    mcp_servers={},
    setting_sources=["project"],
    max_turns=None,
    cwd=None,
    hooks={}
)
```

---

## 8. Hooks Pattern

### Decision: Use hooks for logging and validation

### Rationale
- Clean interception points for logging, validation, and security
- No manual tool handling required
- Aligns with separation of concerns

### Implementation

```python
from claude_agent_sdk import HookMatcher, HookContext

async def pre_tool_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    logger.info(f"Using tool: {input_data.get('tool_name')}")
    return {}  # Allow execution

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(hooks=[pre_tool_hook])],
    }
)
```

---

## 9. Key Imports Summary

```python
from claude_agent_sdk import (
    # Client
    ClaudeSDKClient,
    ClaudeAgentOptions,

    # Messages
    Message, AssistantMessage, UserMessage, SystemMessage, ResultMessage,

    # Content blocks
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,

    # Custom tools
    tool, create_sdk_mcp_server,

    # Hooks
    HookMatcher, HookContext,

    # Errors
    ClaudeSDKError, CLINotFoundError, CLIConnectionError,
    ProcessError, CLIJSONDecodeError
)
```

---

## Sources

- [GitHub - anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [Agent SDK reference - Python - Claude Docs](https://platform.claude.com/docs/en/agent-sdk/python)
- [Agent SDK overview - Claude Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Claude Agent SDK Best Practices (2025)](https://skywork.ai/blog/claude-agent-sdk-best-practices-ai-agents-2025/)
