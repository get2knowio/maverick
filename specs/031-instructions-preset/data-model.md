# Data Model: Instructions Preset

**Feature**: 031-instructions-preset
**Date**: 2026-02-22

## Entities

### MaverickAgent (Interactive Agent Base Class)

**Location**: `src/maverick/agents/base.py`
**Purpose**: Abstract base class for multi-turn, tool-using agents that benefit from Claude Code capabilities.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique identifier for the agent |
| `instructions` | `str` | Yes | Agent-specific role and behavioral guidelines, appended to Claude Code preset |
| `allowed_tools` | `list[str]` | Yes | Tools the agent may use (validated at construction) |
| `model` | `str \| None` | No | Claude model ID (defaults to `CLAUDE_SONNET_LATEST`) |
| `mcp_servers` | `dict[str, Any] \| None` | No | MCP server configurations |
| `max_tokens` | `int \| None` | No | Maximum output tokens |
| `temperature` | `float \| None` | No | Sampling temperature 0.0-1.0 |
| `output_model` | `type[BaseModel] \| None` | No | Pydantic model for structured output enforcement |

**System Prompt Composition**:
```python
{
    "type": "preset",
    "preset": "claude_code",
    "append": self._instructions,  # Agent-specific guidance
}
```

**Setting Sources**: `["project", "user"]` — automatically loads project (CLAUDE.md) and user configuration.

**Validation Rules**:
- `allowed_tools` validated against `BUILTIN_TOOLS` and MCP server patterns at construction time
- `instructions` may be empty (agent operates with preset alone per FR-006)

---

### GeneratorAgent (One-Shot Agent Base Class)

**Location**: `src/maverick/agents/generators/base.py`
**Purpose**: Abstract base class for single-shot text generation agents that do NOT use tools.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique identifier for the generator |
| `system_prompt` | `str` | Yes | Full system prompt (NOT appended to preset) |
| `model` | `str` | No | Claude model ID (defaults to `DEFAULT_MODEL`) |
| `max_tokens` | `int \| None` | No | Maximum output tokens |
| `temperature` | `float \| None` | No | Sampling temperature 0.0-1.0 |

**System Prompt Composition**: Direct string — no preset, no append.
```python
ClaudeAgentOptions(
    system_prompt=self._system_prompt,  # Full system prompt, no preset
    max_turns=1,                        # Single-shot
    allowed_tools=[],                   # No tools
)
```

**Validation Rules**:
- `name` must be non-empty
- `system_prompt` must be non-empty (raises `ValueError`)

---

### SystemPromptPreset (SDK Type)

**Location**: Claude Agent SDK `types.py`
**Purpose**: TypedDict defining the preset configuration for agent system prompts.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `Literal["preset"]` | Yes | Fixed value: `"preset"` |
| `preset` | `Literal["claude_code"]` | Yes | Preset name (currently only `"claude_code"`) |
| `append` | `str` | No (`NotRequired`) | Agent-specific guidance to append |

---

## Relationships

```
MaverickAgent ──uses──▶ SystemPromptPreset (preset + append)
    │                        │
    │                        ├── Claude Code preset (SDK-managed)
    │                        └── Agent instructions (developer-provided)
    │
    ├──loads──▶ SettingSource["project"] (CLAUDE.md, project config)
    └──loads──▶ SettingSource["user"] (user preferences)

GeneratorAgent ──uses──▶ str (direct system_prompt, no preset)
```

## Precedence Order (Lowest → Highest)

1. **Claude Code preset** — universal defaults (tool patterns, safety, code editing)
2. **Project config** — project-specific conventions (CLAUDE.md)
3. **User config** — personal preferences
4. **Agent instructions** — role-specific guidance (highest priority)
