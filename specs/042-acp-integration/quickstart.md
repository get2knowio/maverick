# Quickstart: ACP Integration

**Feature**: 042-acp-integration | **Date**: 2026-03-04

## Prerequisites

- Python 3.10+
- Node.js 18+ (for `npx` — used to spawn Claude Code ACP agent)
- `uv` package manager
- Anthropic API key (`ANTHROPIC_API_KEY` env var)

## Installation

```bash
# Add ACP dependency
uv add agent-client-protocol

# Remove old SDK (after migration complete)
uv remove claude-agent-sdk
```

## Zero-Config Usage (Default)

No configuration changes needed. With no `agent_providers` section in `maverick.yaml`, Maverick automatically uses Claude Code via ACP:

```bash
# Just works — spawns Claude Code via npx
maverick fly
```

## Configuring Agent Providers

Add to `maverick.yaml`:

```yaml
# Explicit Claude Code provider (equivalent to default)
agent_providers:
  claude:
    command: ["npx", "@anthropic-ai/claude-code@latest", "--acp"]
    permission_mode: auto_approve
    default: true

# Optional: second provider (future)
#  gemini:
#    command: ["gemini", "--acp"]
#    permission_mode: auto_approve
```

## Selecting a Provider per Step

```yaml
steps:
  implement:
    provider: claude    # Use the "claude" provider
    timeout: 600
    max_retries: 2
  review:
    provider: claude    # Can be any registered provider name
    timeout: 300
```

## Key Differences from Claude Agent SDK

| Aspect | Before (SDK) | After (ACP) |
|--------|-------------|-------------|
| Dependency | `claude-agent-sdk` | `agent-client-protocol` |
| Agent base class | `MaverickAgent.execute()` + `query()` | `MaverickAgent.build_prompt()` |
| Executor | `ClaudeStepExecutor` | `AcpStepExecutor` |
| Streaming | SDK `StreamEvent` messages | ACP `session_update()` callback |
| Structured output | SDK `ResultMessage.structured_output` | Extract last JSON block from text |
| Multi-provider | Not supported | `agent_providers` config section |
| Permission handling | SDK `permission_mode` string | `Client.request_permission()` callback |
| Connection reuse | New subprocess per step | Cached connection, fresh session per step |

## Code Examples

### Building an Agent Prompt (New Pattern)

```python
from maverick.agents.base import MaverickAgent

class ImplementerAgent(MaverickAgent[ImplementerContext, str]):
    def __init__(self) -> None:
        super().__init__(
            name="implementer",
            instructions="You are a senior software engineer...",
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        )

    def build_prompt(self, context: ImplementerContext) -> str:
        # Pure prompt construction — no SDK interaction
        return f"""
## Task
{context.task_description}

## Working Directory
{context.cwd}

## Instructions
Implement the task described above.
"""
```

### Executor Usage (Workflow Code — Unchanged)

```python
# Workflow code doesn't change — StepExecutor protocol is the same
result = await self._step_executor.execute(
    step_name="implement",
    agent_name="implementer",
    prompt=implementer_context,
    cwd=workspace_path,
    config=step_config,
    event_callback=self._emit_event,
)
```

### Custom Provider Configuration

```python
from maverick.config import AgentProviderConfig, PermissionMode

config = AgentProviderConfig(
    command=["npx", "@anthropic-ai/claude-code@latest", "--acp"],
    env={"ANTHROPIC_API_KEY": "sk-..."},
    permission_mode=PermissionMode.AUTO_APPROVE,
    default=True,
)
```

## Testing

```bash
# Run all tests (ACP mocked, no subprocess spawning)
make test

# Run only ACP-related tests
uv run pytest tests/unit/executor/ -v

# Verify no SDK references remain
uv run grep -r "claude_agent_sdk" src/ tests/ --include="*.py"
# Should return no results
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `CLINotFoundError: npx not found` | Node.js not installed | Install Node.js 18+ |
| `ProcessError: exit code 1` | Agent subprocess failed | Check `ANTHROPIC_API_KEY` is set |
| `MaverickTimeoutError` | Step exceeded timeout | Increase `timeout` in step config |
| `CircuitBreakerError` | Agent in infinite tool loop | Review agent instructions; reduce tool set |
| `ConfigError: multiple defaults` | Two providers marked `default: true` | Fix `maverick.yaml` — exactly one default |
