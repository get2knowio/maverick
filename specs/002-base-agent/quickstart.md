# Quickstart: Base Agent Abstraction Layer

**Feature**: 002-base-agent | **Date**: 2025-12-12

## Prerequisites

- Python 3.10+
- Claude CLI installed: `npm install -g @anthropic-ai/claude-code`
- Claude Agent SDK: `pip install claude-agent-sdk`

## Creating Your First Agent

### Step 1: Define a Concrete Agent

```python
from maverick.agents import MaverickAgent, AgentResult, AgentContext

class GreeterAgent(MaverickAgent):
    """A simple agent that greets users."""

    def __init__(self, model: str | None = None):
        super().__init__(
            name="greeter",
            system_prompt="You are a friendly greeter. Respond with a warm greeting.",
            allowed_tools=[],  # No tools needed for simple greeting
            model=model,
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the greeting task."""
        prompt = f"Greet someone working on the {context.branch} branch."

        # Collect streamed messages
        messages = []
        async for message in self.query(prompt, cwd=context.cwd):
            messages.append(message)

        # Extract text and build result
        from maverick.agents.utils import extract_all_text

        return AgentResult.success_result(
            output=extract_all_text(messages),
            usage=self._extract_usage(messages),
        )
```

### Step 2: Register the Agent

```python
from maverick.agents import registry

# Option 1: Decorator
@registry.register("greeter")
class GreeterAgent(MaverickAgent):
    ...

# Option 2: Explicit registration
registry.register("greeter", GreeterAgent)
```

### Step 3: Use the Agent

```python
import asyncio
from pathlib import Path
from maverick.agents import registry, AgentContext
from maverick.config import MaverickConfig

async def main():
    # Create context
    context = AgentContext(
        cwd=Path.cwd(),
        branch="main",
        config=MaverickConfig(),
    )

    # Instantiate and execute
    agent = registry.create("greeter")
    result = await agent.execute(context)

    if result.success:
        print(f"Output: {result.output}")
        print(f"Tokens: {result.usage.total_tokens}")
    else:
        print(f"Errors: {result.errors}")

asyncio.run(main())
```

## Common Patterns

### Agent with Tools

```python
class CodeReviewerAgent(MaverickAgent):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="code_reviewer",
            system_prompt="You are an expert code reviewer...",
            allowed_tools=["Read", "Grep", "Glob"],  # File access tools
            model=model,
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        file_path = context.extra.get("file_path", "")
        prompt = f"Review the code in {file_path}"
        # ... rest of implementation
```

### Agent with Custom MCP Tools

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("lint_code", "Run linter on code", {"file_path": str})
async def lint_code(args: dict) -> dict:
    # Custom linting logic
    return {"content": [{"type": "text", "text": "Linting complete"}]}

lint_server = create_sdk_mcp_server(
    name="linting",
    version="1.0.0",
    tools=[lint_code],
)

class LintingAgent(MaverickAgent):
    def __init__(self):
        super().__init__(
            name="linter",
            system_prompt="You are a code quality assistant...",
            allowed_tools=["mcp__linting__lint_code"],
            mcp_servers={"linting": lint_server},
        )
```

### Streaming for TUI Integration

```python
async def display_streaming_response(agent: MaverickAgent, prompt: str):
    """Display agent response in real-time."""
    from maverick.agents.utils import extract_text
    from claude_agent_sdk import AssistantMessage

    async for message in agent.query(prompt):
        if isinstance(message, AssistantMessage):
            text = extract_text(message)
            print(text, end="", flush=True)
    print()  # Final newline
```

## Error Handling

```python
from maverick.exceptions import (
    CLINotFoundError,
    ProcessError,
    StreamingError,
    InvalidToolError,
)

async def safe_execute(agent: MaverickAgent, context: AgentContext):
    try:
        result = await agent.execute(context)
        return result
    except CLINotFoundError as e:
        print(f"Claude CLI not found: {e}")
        print("Install with: npm install -g @anthropic-ai/claude-code")
    except ProcessError as e:
        print(f"Process failed (exit {e.exit_code}): {e.stderr}")
    except StreamingError as e:
        print(f"Streaming failed: {e}")
        # Partial messages may be available in e.partial_messages
    except InvalidToolError as e:
        print(f"Invalid tool '{e.tool_name}'")
        print(f"Available: {e.available_tools}")
```

## Testing Agents

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_greeter_agent():
    # Arrange
    agent = GreeterAgent()
    context = AgentContext(
        cwd=Path("/tmp"),
        branch="test-branch",
        config=MaverickConfig(),
    )

    # Mock the query method
    agent.query = AsyncMock(return_value=iter([
        MagicMock(content=[MagicMock(text="Hello!")])
    ]))

    # Act
    result = await agent.execute(context)

    # Assert
    assert result.success
    assert "Hello" in result.output
```

## Next Steps

1. See `data-model.md` for complete entity definitions
2. See `contracts/agent_protocol.py` for interface specifications
3. See `research.md` for SDK patterns and best practices
