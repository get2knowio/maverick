---
layout: section
class: text-center
---

# 10. Claude Agent SDK - AI Agent Development

<div class="text-lg text-secondary mt-4">
Building AI-powered agents with the Model Context Protocol
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">9 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">MCP Architecture</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Tool Development</span>
  </div>
</div>

<!--
Section 10 covers the Claude Agent SDK - the AI backbone of Maverick.

We'll cover:
1. What is MCP (Model Context Protocol)
2. Claude Agent SDK overview
3. Defining tools with the @tool decorator
4. Tool parameter schemas
5. Tool response patterns
6. Creating MCP servers
7. Agent execution
8. Streaming responses
9. Built-in tools
-->

---

## layout: two-cols

# 10.1 What is MCP?

<div class="pr-4">

**Model Context Protocol** (MCP) is a standard for AI tool integration

<div v-click class="mt-4">

## The Problem

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>Fragmented Tool Ecosystems</strong>
    <div class="text-muted">Every AI has its own tool format</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>No Standard Interface</strong>
    <div class="text-muted">Hard to share tools across agents</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>Tight Coupling</strong>
    <div class="text-muted">Tools embedded in agent code</div>
  </div>
</div>

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## MCP Solution ✓

```
┌─────────────────────────────────────┐
│           Claude Agent              │
│                                     │
│  ┌─────────────────────────────┐   │
│  │     MCP Protocol Layer      │   │
│  └─────────────────────────────┘   │
│              ↕                      │
│  ┌─────────┐ ┌─────────┐ ┌─────┐  │
│  │  Tool   │ │  Tool   │ │ ... │  │
│  │ Server  │ │ Server  │ │     │  │
│  └─────────┘ └─────────┘ └─────┘  │
│       ↓           ↓                 │
│    Git API    GitHub API            │
└─────────────────────────────────────┘
```

</div>

<div v-click class="mt-4">

## Key Concepts

<div class="grid grid-cols-2 gap-2 text-xs mt-2">
  <div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
    <strong class="text-teal">Tools</strong>
    <div class="text-muted">Functions the AI can call</div>
  </div>
  <div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
    <strong class="text-brass">Servers</strong>
    <div class="text-muted">Groups of related tools</div>
  </div>
  <div class="p-2 bg-coral/10 border border-coral/30 rounded-lg">
    <strong class="text-coral">Resources</strong>
    <div class="text-muted">Data the AI can access</div>
  </div>
  <div class="p-2 bg-success/10 border border-success/30 rounded-lg">
    <strong class="text-success">Prompts</strong>
    <div class="text-muted">Reusable AI templates</div>
  </div>
</div>

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Maverick Uses MCP</strong> to give Claude access to git, GitHub, validation, and notification tools via separate MCP servers.
</div>

</div>

<!--
The Model Context Protocol (MCP) solves the fragmentation problem in AI tool ecosystems.

Before MCP:
- Every AI system had its own tool format
- Tools couldn't be shared or reused
- Tool code was tightly coupled to agent code

MCP provides:
- **Tools**: Functions that AI can invoke with typed parameters
- **Servers**: Logical groupings of related tools
- **Resources**: Data sources the AI can read from
- **Prompts**: Reusable prompt templates

Maverick uses MCP extensively - our git-tools, github-tools, validation-tools, and notification-tools are all MCP servers.
-->

---

## layout: default

# 10.2 Claude Agent SDK Overview

<div class="text-secondary text-sm mb-4">
The Python SDK for building Claude-powered agents
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Installation

```bash
pip install claude-agent-sdk
# or with uv
uv add claude-agent-sdk
```

</div>

<div v-click class="mt-4">

### Key Imports

```python
from claude_agent_sdk import (
    # Tool definition
    tool,
    create_sdk_mcp_server,

    # Client and options
    ClaudeSDKClient,
    ClaudeAgentOptions,

    # Types
    Message,
)
```

</div>

<div v-click class="mt-4">

### Environment Setup

```bash
# Required: Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

</div>

</div>

<div>

<div v-click>

### SDK Architecture

```
┌──────────────────────────────┐
│      ClaudeSDKClient         │
│  ┌────────────────────────┐  │
│  │   ClaudeAgentOptions   │  │
│  │  - system_prompt       │  │
│  │  - allowed_tools       │  │
│  │  - mcp_servers         │  │
│  │  - model               │  │
│  │  - permission_mode     │  │
│  └────────────────────────┘  │
│              ↓                │
│  ┌────────────────────────┐  │
│  │      query(prompt)     │  │
│  │            ↓           │  │
│  │  receive_response()    │  │
│  │     (async iter)       │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Async-First</strong>: The SDK uses async/await patterns throughout. All agent interactions are asynchronous for non-blocking execution.
</div>

</div>

</div>

<!--
The Claude Agent SDK provides the Python interface for building AI agents.

**Installation**: Simple pip/uv install. Maverick includes it as a dependency.

**Key components**:
- `tool` decorator for defining callable functions
- `create_sdk_mcp_server` for grouping tools
- `ClaudeSDKClient` for running agents
- `ClaudeAgentOptions` for configuration

**Environment**: Requires `ANTHROPIC_API_KEY` for API access.

The SDK is entirely async-first, matching Maverick's async architecture.
-->

---

## layout: default

# 10.3 Defining Tools

<div class="text-secondary text-sm mb-4">
The <code>@tool</code> decorator transforms functions into MCP tools
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Basic Tool Definition

```python {all|1-5|7-18|all}
from claude_agent_sdk import tool

@tool(
    "greet_user",                # Tool name
    "Greet a user by name",      # Description
    {"name": str},               # Parameter schema
)
async def greet_user(
    args: dict[str, Any]
) -> dict[str, Any]:
    """Greet a user by name.

    Args:
        args: Dict with 'name' key.

    Returns:
        MCP response with greeting.
    """
    name = args.get("name", "World")
    return {
        "content": [{
            "type": "text",
            "text": f"Hello, {name}!"
        }]
    }
```

</div>

</div>

<div>

<div v-click>

### The Three Arguments

<div class="space-y-3 text-sm mt-3">

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <strong class="text-teal">1. Name (str)</strong>
  <div class="text-muted">Unique identifier. Use snake_case. This is how Claude calls the tool.</div>
</div>

<div class="p-3 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass">2. Description (str)</strong>
  <div class="text-muted">Explains what the tool does. Claude uses this to decide when to call it.</div>
</div>

<div class="p-3 bg-coral/10 border border-coral/30 rounded-lg">
  <strong class="text-coral">3. Schema (dict)</strong>
  <div class="text-muted">Parameter types. Maps param names to Python types (<code>str</code>, <code>int</code>, <code>bool</code>, <code>list</code>, etc.)</div>
</div>

</div>

</div>

<div v-click class="mt-4">

### Maverick Example

```python
# From maverick/tools/validation.py
@tool(
    "run_validation",
    "Run project validation commands "
    "(format, lint, typecheck, test)",
    {"types": list},  # list of validation types
)
async def run_validation(args: dict[str, Any]):
    types_to_run = args.get("types", [])
    # ... validation logic
```

</div>

</div>

</div>

<!--
The @tool decorator is the core of MCP tool development.

**Three required arguments**:
1. **Name**: The identifier Claude uses to call the tool. Use snake_case.
2. **Description**: Critical! Claude reads this to understand when to use the tool.
3. **Schema**: Parameter types. The SDK validates incoming args against this.

**Function signature**: Always `async def` with `args: dict[str, Any]` parameter.

**Return format**: MCP response dict with `content` array containing text blocks.

The Maverick validation tool shows a real example - it takes a list of validation types to run.
-->

---

## layout: default

# 10.4 Tool Parameters

<div class="text-secondary text-sm mb-4">
Schema definitions for tool inputs
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Supported Types

```python {all|2-5|7-10|12-15|all}
# Basic types
{"message": str}        # String
{"count": int}          # Integer
{"ratio": float}        # Float
{"enabled": bool}       # Boolean

# Collection types
{"items": list}         # List
{"config": dict}        # Dictionary
{"tags": tuple}         # Tuple

# Optional via default handling
# All params are technically optional
# - validate in function body
# - provide sensible defaults
```

</div>

<div v-click class="mt-4">

### Extracting Args

```python
@tool("process", "Process items",
      {"items": list, "limit": int})
async def process(args: dict[str, Any]):
    # With defaults
    items = args.get("items", [])
    limit = args.get("limit", 10)

    # Required (raise on missing)
    if "items" not in args:
        return error_response(
            "items is required",
            "MISSING_PARAM"
        )
```

</div>

</div>

<div>

<div v-click>

### Real Maverick Example

```python
# From maverick/tools/git/tools/commit.py
@tool(
    "git_commit",
    "Create a git commit with conventional "
    "commit format",
    {
        "message": str,    # Required
        "type": str,       # Optional: feat, fix, etc.
        "scope": str,      # Optional: component name
        "breaking": bool,  # Optional: breaking change
    },
)
async def git_commit(args: dict[str, Any]):
    # Extract with validation
    message = args.get("message", "").strip()
    commit_type = args.get("type")
    scope = args.get("scope")
    breaking = args.get("breaking", False)

    # Validate required params
    if not message:
        return error_response(
            "Commit message cannot be empty",
            "INVALID_INPUT"
        )

    # Validate enum values
    if commit_type and commit_type not in COMMIT_TYPES:
        return error_response(
            f"Invalid type '{commit_type}'",
            "INVALID_INPUT"
        )
```

</div>

</div>

</div>

<!--
Tool parameter schemas define what input the tool accepts.

**Supported types**: Basic Python types - str, int, float, bool, list, dict, tuple.

**No optional syntax**: The schema doesn't distinguish required vs optional. Handle this in your function:
- Use `args.get("param", default)` for optional params
- Validate and return error responses for missing required params

**Maverick pattern**: Our git_commit tool shows the pattern:
1. Extract all args with sensible defaults
2. Validate required params early
3. Validate enum/constrained values
4. Return error_response for invalid input (never raise)
-->

---

## layout: default

# 10.5 Tool Responses

<div class="text-secondary text-sm mb-4">
Structured response patterns for MCP tools
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Success Response Format

```python
# Standard MCP success response
{
    "content": [
        {
            "type": "text",
            "text": "Operation completed successfully"
        }
    ]
}

# With structured data (as JSON string)
{
    "content": [
        {
            "type": "text",
            "text": json.dumps({
                "success": True,
                "commit_sha": "abc123",
                "message": "feat: add feature"
            })
        }
    ]
}
```

</div>

<div v-click class="mt-4">

### Error Response Format

```python
# MCP error response
{
    "isError": True,
    "content": [
        {
            "type": "text",
            "text": json.dumps({
                "error": "File not found",
                "error_code": "FILE_NOT_FOUND"
            })
        }
    ]
}
```

</div>

</div>

<div>

<div v-click>

### Maverick Response Helpers

```python
# From maverick/tools/git/responses.py

def success_response(data: dict[str, Any]) -> dict:
    """Create MCP success response."""
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(data),
        }]
    }

def error_response(
    message: str,
    code: str
) -> dict:
    """Create MCP error response."""
    return {
        "isError": True,
        "content": [{
            "type": "text",
            "text": json.dumps({
                "error": message,
                "error_code": code,
            }),
        }]
    }
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Never Raise Exceptions!</strong> Tools must always return a response dict. Catch all exceptions and convert to error_response.
</div>

<div v-click class="mt-2 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Always JSON</strong>: Put structured data in the text field as JSON strings. This enables Claude to parse and reason about the results.
</div>

</div>

</div>

<!--
MCP tools must return structured responses in a specific format.

**Success responses**:
- `content` array with text blocks
- Structured data as JSON strings in the text field
- Claude can parse JSON to understand results

**Error responses**:
- `isError: True` flag
- Error message and code in the content
- Claude knows to handle the error or retry

**Critical rule**: Never raise exceptions from tools! Always catch errors and return error_response. Exceptions break the MCP protocol.

Maverick provides helper functions (success_response, error_response) to ensure consistent formatting.
-->

---

## layout: default

# 10.6 Creating MCP Servers

<div class="text-secondary text-sm mb-4">
Grouping tools into logical servers with <code>create_sdk_mcp_server</code>
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Server Factory Pattern

```python {all|1-2|4-20|22-28|all}
from claude_agent_sdk import (
    create_sdk_mcp_server, tool
)

@tool("git_commit", "Create commit",
      {"message": str})
async def git_commit(args):
    # ... implementation
    pass

@tool("git_push", "Push to remote",
      {"remote": str, "branch": str})
async def git_push(args):
    # ... implementation
    pass

@tool("git_status", "Get repo status", {})
async def git_status(args):
    # ... implementation
    pass

# Group tools into a server
server = create_sdk_mcp_server(
    name="git-tools",
    version="1.0.0",
    tools=[git_commit, git_push, git_status],
)
```

</div>

</div>

<div>

<div v-click>

### Maverick's Server Pattern

```python
# maverick/tools/git/server.py
def create_git_tools_server(
    cwd: Path | None = None,
) -> McpSdkServerConfig:
    """Factory function with closure."""

    # Capture config in closure
    _cwd = cwd

    # Create tool functions
    git_commit = create_git_commit_tool(_cwd)
    git_push = create_git_push_tool(_cwd)
    git_current_branch = create_git_current_branch_tool(_cwd)

    # Create server with all tools
    return create_sdk_mcp_server(
        name="git-tools",
        version="1.0.0",
        tools=[
            git_commit,
            git_push,
            git_current_branch,
        ],
    )
```

</div>

<div v-click class="mt-4">

### Maverick MCP Servers

<div class="grid grid-cols-2 gap-2 text-xs mt-2">
  <div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
    <strong class="text-teal">git-tools</strong>
    <div class="text-muted">commit, push, branch, diff</div>
  </div>
  <div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
    <strong class="text-brass">github-tools</strong>
    <div class="text-muted">PR, issues, labels</div>
  </div>
  <div class="p-2 bg-coral/10 border border-coral/30 rounded-lg">
    <strong class="text-coral">validation-tools</strong>
    <div class="text-muted">lint, format, test, typecheck</div>
  </div>
  <div class="p-2 bg-success/10 border border-success/30 rounded-lg">
    <strong class="text-success">notification-tools</strong>
    <div class="text-muted">ntfy push notifications</div>
  </div>
</div>

</div>

</div>

</div>

<!--
MCP servers group related tools together.

**create_sdk_mcp_server** takes:
- `name`: Server identifier (used in tool paths like `mcp__git-tools__git_commit`)
- `version`: Server version string
- `tools`: List of @tool decorated functions

**Maverick pattern**: Factory functions with closures. This allows:
- Configuration (like working directory) to be captured
- No global state
- Easy testing with different configs

**Maverick's four servers**:
1. git-tools: Git operations (commit, push, branch, diff)
2. github-tools: GitHub API (PRs, issues, labels)
3. validation-tools: Code quality (lint, format, test, typecheck)
4. notification-tools: Push notifications via ntfy
-->

---

## layout: default

# 10.7 Agent Execution

<div class="text-secondary text-sm mb-4">
Running agents with <code>ClaudeSDKClient</code>
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Direct SDK Usage

```python {all|1-3|5-15|17-25|all}
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions
)

# Configure the agent
options = ClaudeAgentOptions(
    system_prompt="You are a helpful assistant.",
    allowed_tools=["Read", "Write"],
    model="claude-sonnet-4-5-20250929",
    permission_mode="acceptEdits",
    mcp_servers={
        "git": create_git_tools_server(),
    },
    cwd="/path/to/project",
)

# Run a query
async with ClaudeSDKClient(options=options) as client:
    await client.query("Summarize the README.md")

    # Stream responses
    async for message in client.receive_response():
        if message.content:
            for block in message.content:
                print(block.text)
```

</div>

</div>

<div>

<div v-click>

### Maverick's MaverickAgent

```python
# From maverick/agents/base.py
class MaverickAgent(ABC, Generic[TContext, TResult]):
    def __init__(
        self,
        name: str,
        system_prompt: str,
        allowed_tools: list[str],
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ):
        # Validate tools at construction
        self._validate_tools(allowed_tools, mcp_servers)

    async def query(
        self,
        prompt: str,
        cwd: Path | None = None
    ) -> AsyncIterator[Message]:
        """Stream messages from Claude."""
        options = self._build_options(cwd)

        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                yield message

    @abstractmethod
    async def execute(self, context: TContext) -> TResult:
        """Subclasses implement task logic."""
        ...
```

</div>

</div>

</div>

<!--
Agent execution involves creating a client, sending a query, and streaming responses.

**Direct SDK usage**:
1. Create ClaudeAgentOptions with config
2. Use async context manager for ClaudeSDKClient
3. Call query() with prompt
4. Iterate receive_response() for messages

**Maverick's MaverickAgent**:
- Wraps SDK client lifecycle
- Validates tools at construction time
- Provides `query()` helper that handles streaming
- Abstract `execute()` method for concrete agents to implement

**Key configuration**:
- `allowed_tools`: What Claude can use (validated against BUILTIN_TOOLS + MCP tools)
- `mcp_servers`: Custom tool servers
- `permission_mode`: How Claude handles file edits (acceptEdits for automation)
-->

---

## layout: default

# 10.8 Streaming Responses

<div class="text-secondary text-sm mb-4">
Real-time output from Claude
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Message Types

```python
# Claude streams various message types
async for message in client.receive_response():
    # Assistant messages with content
    if message.role == "assistant":
        for block in message.content:
            if block.type == "text":
                print(block.text)
            elif block.type == "tool_use":
                print(f"Calling: {block.name}")

    # Tool results
    elif message.role == "tool_result":
        print(f"Tool result: {message.content}")
```

</div>

<div v-click class="mt-4">

### Token-by-Token Streaming

```python
# Enable with include_partial_messages=True
options = ClaudeAgentOptions(
    # ... other options
    include_partial_messages=True,
)

# Receive incremental text
async for message in client.receive_response():
    # Partial messages arrive as Claude types
    # Great for real-time TUI updates
    pass
```

</div>

</div>

<div>

<div v-click>

### Maverick Streaming Pattern

```python
# From maverick/agents/base.py

StreamCallback = Callable[
    [str],
    Coroutine[Any, Any, None]
]

class MaverickAgent:
    _stream_callback: StreamCallback | None = None

    async def query(self, prompt: str, ...):
        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                # Notify callback for TUI updates
                if self._stream_callback and message.content:
                    for block in message.content:
                        if hasattr(block, 'text'):
                            await self._stream_callback(
                                block.text
                            )
                yield message
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">TUI Integration</strong>: The stream callback allows Maverick's Textual TUI to display Claude's responses in real-time as they stream in.
</div>

</div>

</div>

<!--
Streaming enables real-time output as Claude generates responses.

**Message types**:
- **Assistant messages**: Claude's text output and tool calls
- **Tool results**: Responses from tool invocations

**Token-by-token streaming**: With `include_partial_messages=True`, you receive incremental text as Claude "types" - essential for responsive UIs.

**Maverick pattern**:
- Optional `StreamCallback` for real-time updates
- Used by TUI to show Claude's thinking as it happens
- Messages are still yielded for full processing

This is how the Maverick TUI shows streaming output - it connects a callback to update the display widget.
-->

---

## layout: default

# 10.9 Built-in Tools

<div class="text-secondary text-sm mb-4">
Claude's native capabilities
</div>

<div class="grid grid-cols-3 gap-4">

<div v-click>

### File Operations

<div class="space-y-2 text-sm mt-3">

<div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
  <strong class="text-teal font-mono text-xs">Read</strong>
  <div class="text-muted text-xs">Read file contents</div>
</div>

<div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
  <strong class="text-teal font-mono text-xs">Write</strong>
  <div class="text-muted text-xs">Create/overwrite files</div>
</div>

<div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
  <strong class="text-teal font-mono text-xs">Edit</strong>
  <div class="text-muted text-xs">Modify file sections</div>
</div>

<div class="p-2 bg-teal/10 border border-teal/30 rounded-lg">
  <strong class="text-teal font-mono text-xs">NotebookEdit</strong>
  <div class="text-muted text-xs">Edit Jupyter notebooks</div>
</div>

</div>

</div>

<div v-click>

### Search & Execute

<div class="space-y-2 text-sm mt-3">

<div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass font-mono text-xs">Bash</strong>
  <div class="text-muted text-xs">Run shell commands</div>
</div>

<div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass font-mono text-xs">Glob</strong>
  <div class="text-muted text-xs">Find files by pattern</div>
</div>

<div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass font-mono text-xs">Grep</strong>
  <div class="text-muted text-xs">Search file contents</div>
</div>

<div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass font-mono text-xs">WebFetch</strong>
  <div class="text-muted text-xs">Fetch web content</div>
</div>

<div class="p-2 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass font-mono text-xs">WebSearch</strong>
  <div class="text-muted text-xs">Search the web</div>
</div>

</div>

</div>

<div v-click>

### Agent Control

<div class="space-y-2 text-sm mt-3">

<div class="p-2 bg-coral/10 border border-coral/30 rounded-lg">
  <strong class="text-coral font-mono text-xs">Task</strong>
  <div class="text-muted text-xs">Spawn sub-agent tasks</div>
</div>

<div class="p-2 bg-coral/10 border border-coral/30 rounded-lg">
  <strong class="text-coral font-mono text-xs">TodoWrite</strong>
  <div class="text-muted text-xs">Update task lists</div>
</div>

<div class="p-2 bg-coral/10 border border-coral/30 rounded-lg">
  <strong class="text-coral font-mono text-xs">ExitPlanMode</strong>
  <div class="text-muted text-xs">Exit planning mode</div>
</div>

</div>

<div class="mt-4 p-3 bg-success/10 border border-success/30 rounded-lg text-xs">
  <strong class="text-success">12 Built-in Tools</strong>
  <div class="text-muted mt-1">These are always available (when allowed) without any MCP server setup.</div>
</div>

</div>

</div>

<div v-click class="mt-6">

### Maverick's BUILTIN_TOOLS Constant

```python
# From maverick/agents/base.py
BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "NotebookEdit", "WebFetch", "WebSearch",
    "TodoWrite", "Task", "ExitPlanMode",
})
```

<div class="text-xs text-muted mt-2">
Agents specify allowed tools from this set (plus their MCP tools). Maverick validates at construction time.
</div>

</div>

<!--
Claude comes with 12 built-in tools that don't require MCP setup.

**File Operations**:
- Read: Read file contents
- Write: Create or overwrite files
- Edit: Make targeted edits to file sections
- NotebookEdit: Edit Jupyter notebooks

**Search & Execute**:
- Bash: Run shell commands
- Glob: Find files matching patterns
- Grep: Search file contents
- WebFetch/WebSearch: Internet access

**Agent Control**:
- Task: Spawn sub-agent tasks
- TodoWrite: Update task lists
- ExitPlanMode: Exit planning mode

Maverick's BUILTIN_TOOLS constant defines these. When creating an agent, you specify which builtins to allow. Tool validation happens at construction time.
-->

---

layout: center
class: text-center

---

# Section 10 Summary

<div class="grid grid-cols-3 gap-6 mt-8 max-w-4xl mx-auto">

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">🔌</div>
  <h3 class="text-sm font-semibold mb-2">MCP Protocol</h3>
  <p class="text-xs text-muted">Standard interface for AI tools - servers, tools, resources, and prompts</p>
</div>

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">🛠️</div>
  <h3 class="text-sm font-semibold mb-2">@tool Decorator</h3>
  <p class="text-xs text-muted">Name, description, schema → async function → MCP response</p>
</div>

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">📦</div>
  <h3 class="text-sm font-semibold mb-2">MCP Servers</h3>
  <p class="text-xs text-muted">Group tools logically with create_sdk_mcp_server()</p>
</div>

</div>

<div class="grid grid-cols-3 gap-6 mt-4 max-w-4xl mx-auto">

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">🤖</div>
  <h3 class="text-sm font-semibold mb-2">MaverickAgent</h3>
  <p class="text-xs text-muted">ABC wrapping ClaudeSDKClient with tool validation</p>
</div>

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">📡</div>
  <h3 class="text-sm font-semibold mb-2">Streaming</h3>
  <p class="text-xs text-muted">Real-time responses with async iteration and callbacks</p>
</div>

<div v-click class="feature-card p-4">
  <div class="text-3xl mb-2">🧰</div>
  <h3 class="text-sm font-semibold mb-2">Built-in Tools</h3>
  <p class="text-xs text-muted">12 native tools: Read, Write, Edit, Bash, Glob, Grep...</p>
</div>

</div>

<div v-click class="mt-8 text-sm text-muted">
  Next: Part 2 - Maverick Architecture
</div>

<!--
Section 10 covered the Claude Agent SDK fundamentals:

1. **MCP Protocol**: The standard for AI tool integration
2. **@tool Decorator**: Transform async functions into callable tools
3. **MCP Servers**: Group related tools together
4. **MaverickAgent**: Our ABC that wraps SDK complexity
5. **Streaming**: Real-time response handling for TUI
6. **Built-in Tools**: 12 native capabilities Claude provides

With this foundation, you can now understand how Maverick's agents leverage Claude for AI-powered development automation.

Next up: Part 2 covers Maverick's internal architecture - how all these pieces fit together.
-->
