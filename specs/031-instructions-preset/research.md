# Research: Instructions Preset

**Feature**: 031-instructions-preset
**Date**: 2026-02-22

## Research Question 1: Claude Agent SDK Preset API

**Decision**: Use `SystemPromptPreset` TypedDict with `{"type": "preset", "preset": "claude_code", "append": instructions}`.

**Rationale**: This is the SDK's native API for composing a base preset with agent-specific guidance. The `append` field is `NotRequired[str]`, allowing agents with no instructions to use the preset alone (FR-006).

**Alternatives considered**:
- Raw `system_prompt: str` — rejected; loses Claude Code built-in capabilities (tool patterns, safety guardrails)
- Custom prompt composition — rejected; reinvents what the SDK provides natively

**SDK Source**: `/workspaces/maverick/.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py` lines 27-32

```python
class SystemPromptPreset(TypedDict):
    type: Literal["preset"]
    preset: Literal["claude_code"]
    append: NotRequired[str]
```

## Research Question 2: Setting Sources for Project/User Config

**Decision**: Use `setting_sources: ["project", "user"]` in `ClaudeAgentOptions`.

**Rationale**: The SDK's `SettingSource` literal type supports `"user"`, `"project"`, and `"local"`. Passing `["project", "user"]` makes the SDK automatically load project-level config (e.g., CLAUDE.md) and user-level config without Maverick needing custom file loading.

**Alternatives considered**:
- `FileSource` class — does not exist in current SDK; `SettingSource` literal is the correct API
- Custom config loading via Maverick's own config system — rejected per clarification (use SDK-native)
- Including `"local"` in sources — unnecessary; project + user covers the required precedence layers

**SDK Source**: `/workspaces/maverick/.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py` line 24

```python
SettingSource = Literal["user", "project", "local"]
```

## Research Question 3: Parameter Naming — `instructions` vs `system_prompt`

**Decision**: `instructions` for interactive agents (MaverickAgent); `system_prompt` for one-shot generators (GeneratorAgent).

**Rationale**:
- Interactive agents (MaverickAgent): The parameter is named `instructions` because it is appended to the Claude Code preset — it is NOT the full system prompt. The name signals that this is additive guidance, not a replacement.
- One-shot generators (GeneratorAgent): The parameter remains `system_prompt` because generators do NOT use the preset. They receive their entire system prompt directly. The name accurately reflects the parameter's role.

**Alternatives considered**:
- Naming both `instructions` — rejected; generators genuinely set the entire system prompt, not just appended guidance
- Naming both `system_prompt` — rejected; for interactive agents this would misleadingly imply the parameter replaces the preset

## Research Question 4: Precedence Order

**Decision**: Preset → Project config → User config → Agent `instructions` (highest priority).

**Rationale**: The most specific layer wins. The Claude Code preset provides universal defaults. Project config (CLAUDE.md) adds project-specific conventions. User config adds personal preferences. Agent instructions are the most specific, describing the agent's exact role and constraints.

**How it works technically**:
1. `system_prompt.preset = "claude_code"` — SDK loads the Claude Code preset as the foundation
2. `setting_sources = ["project", "user"]` — SDK loads and applies project and user settings
3. `system_prompt.append = instructions` — SDK appends agent-specific guidance to the preset

## Research Question 5: Current Implementation Status

**Decision**: The feature is already implemented in the codebase. Remaining work is verification and test coverage.

**Evidence**:

| Requirement | Status | Location |
|-------------|--------|----------|
| FR-001: Interactive agents use preset | DONE | `base.py:273-277` — `system_prompt: {"type": "preset", "preset": "claude_code", "append": ...}` |
| FR-002: Instructions appended to preset | DONE | `base.py:276` — `"append": self._instructions` |
| FR-003: Parameter named `instructions` | DONE | `base.py:132` — `instructions: str` parameter |
| FR-004: SDK-native project/user config | DONE | `base.py:278` — `"setting_sources": ["project", "user"]` |
| FR-005: Generators use direct system_prompt | DONE | `generators/base.py:163` — `system_prompt=self._system_prompt` (no preset) |
| FR-006: Empty instructions works | NEEDS TEST | Parameter accepts empty string, but no explicit test for this scenario |
| FR-007: All concrete agents updated | DONE | All interactive agents pass `instructions` to `MaverickAgent.__init__()` |

**Test gaps identified**:
- No test for empty `instructions` string (FR-006)
- No test verifying `setting_sources` is `["project", "user"]` specifically (FR-004) — the existing test in `test_base.py:327` does verify this
- No test that generators do NOT include preset (negative test for FR-005)
- No documentation of the preset + instructions pattern for new agent authors

**Rationale for "already implemented"**: The `base.py` constructor accepts `instructions`, the `_build_options()` method uses the preset pattern, and all concrete agents (implementer, fixer, issue_fixer, code_reviewer) pass their guidance as `instructions`. This was likely implemented as part of the agent base class design.
