# Contract: Agent Construction

**Feature**: 031-instructions-preset
**Date**: 2026-02-22

## MaverickAgent Construction Contract

### Constructor Signature

```python
MaverickAgent.__init__(
    self,
    name: str,                          # Required, non-empty
    instructions: str,                  # Required, may be empty
    allowed_tools: list[str],           # Required, validated against BUILTIN_TOOLS
    model: str | None = None,           # Defaults to CLAUDE_SONNET_LATEST
    mcp_servers: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    output_model: type[BaseModel] | None = None,
)
```

### System Prompt Output Contract

`_build_options()` MUST produce:

```python
ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": self._instructions,   # Exact value from constructor
    },
    setting_sources=["project", "user"],  # Always these two, in this order
    # ... other fields
)
```

### Invariants

1. `system_prompt` is ALWAYS a `SystemPromptPreset` dict, never a raw string
2. `setting_sources` is ALWAYS `["project", "user"]`
3. `instructions` is stored immutably — the property returns the original value
4. Empty `instructions` is valid — the preset alone is sufficient

---

## GeneratorAgent Construction Contract

### Constructor Signature

```python
GeneratorAgent.__init__(
    self,
    name: str,                # Required, non-empty (ValueError if empty)
    system_prompt: str,       # Required, non-empty (ValueError if empty)
    model: str = DEFAULT_MODEL,
    max_tokens: int | None = None,
    temperature: float | None = None,
)
```

### System Prompt Output Contract

`_build_options()` MUST produce:

```python
ClaudeAgentOptions(
    system_prompt=self._system_prompt,  # Raw string, NOT a preset dict
    max_turns=1,                        # Always single-shot
    allowed_tools=[],                   # Always empty (no tools)
    # ... other fields
)
```

### Invariants

1. `system_prompt` is ALWAYS a raw string, never a `SystemPromptPreset` dict
2. `max_turns` is ALWAYS 1
3. `allowed_tools` is ALWAYS empty
4. No `setting_sources` — generators don't load project/user config
