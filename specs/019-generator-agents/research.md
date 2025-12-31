# Research: Generator Agents

**Branch**: `019-generator-agents` | **Date**: 2025-12-18
**Purpose**: Resolve technical unknowns for single-shot text generation using Claude Agent SDK

## Research Tasks

### 1. Claude Agent SDK `query()` Function

**Question**: How to use `query()` for single-shot text generation without tools?

**Decision**: Use `query()` with `ClaudeAgentOptions(max_turns=1, allowed_tools=[])` for stateless single-shot generation.

**Rationale**: The Claude Agent SDK provides two interfaces:
- `query()`: Async function for single-shot, stateless queries (ideal for generators)
- `ClaudeSDKClient`: Full-featured client for multi-turn, stateful interactions

The `query()` function is explicitly designed for one-shot use cases. Per the spec (FR-002, FR-003), generators should use `query()` with `max_turns=1` and no tools.

**Alternatives Considered**:
1. **ClaudeSDKClient**: Rejected because it's designed for stateful interactions; overkill for generators
2. **Direct Anthropic API**: Rejected because it requires manual tool loop implementation; Agent SDK handles this

**Implementation Pattern**:
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

async def generate(prompt: str, system_prompt: str) -> str:
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=1,
        allowed_tools=[],  # No tools for generators
    )

    text_parts = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

    return "\n".join(text_parts)
```

### 2. Text Extraction from Claude Responses

**Question**: How to reliably extract plain text from Claude SDK message objects?

**Decision**: Iterate through `AssistantMessage.content` blocks, filtering for `TextBlock` instances.

**Rationale**: The existing `extract_text()` and `extract_all_text()` utilities in `src/maverick/agents/utils.py` already implement this pattern using duck-typing (checking `type(block).__name__`). For generators, we can either:
1. Reuse existing utilities (recommended for consistency)
2. Use SDK-provided types directly with `isinstance()` checks

**Implementation Pattern**:
```python
from claude_agent_sdk import AssistantMessage, TextBlock

# Option A: Reuse existing utility
from maverick.agents.utils import extract_all_text
text = extract_all_text(messages)

# Option B: Direct type checking (cleaner for new code)
for message in messages:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                yield block.text
```

**Recommendation**: Use existing `extract_all_text()` for consistency with codebase patterns.

### 3. Error Handling for Generators

**Question**: How should generators handle Claude API errors?

**Decision**: Raise exceptions immediately without retry (per FR-018); let caller handle retry logic.

**Rationale**: The spec explicitly states generators should fail immediately on API errors. This follows the principle of single responsibility - generators generate, workflows orchestrate (including retries).

**Available SDK Exceptions**:
```python
from claude_agent_sdk import (
    ClaudeSDKError,        # Base error
    CLINotFoundError,      # Claude Code not installed
    CLIConnectionError,    # Connection issues
    ProcessError,          # Process failed
    CLIJSONDecodeError,    # JSON parsing issues
)
```

**Implementation Pattern**:
```python
async def generate(self, context: dict) -> str:
    try:
        async for message in query(prompt=self._build_prompt(context), options=self._options):
            # Process messages...
            pass
    except CLINotFoundError:
        raise GeneratorError("Claude CLI not found") from e
    except (CLIConnectionError, ProcessError) as e:
        raise GeneratorError(f"Claude API error: {e}") from e
    # Let other exceptions propagate
```

### 4. Input Truncation Strategy

**Question**: How to handle inputs exceeding size limits (100KB diff, 10KB snippet)?

**Decision**: Truncate with warning log, preserving meaningful content.

**Rationale**: Per FR-017, generators must truncate oversized inputs and log a WARNING. The 018-context-builder module provides `truncate_file()` which preserves context around important lines. For diffs, simple head truncation is acceptable since diffs are linear.

**Implementation Pattern**:
```python
MAX_DIFF_SIZE = 100 * 1024  # 100KB
MAX_SNIPPET_SIZE = 10 * 1024  # 10KB

def _truncate_input(content: str, max_size: int, name: str) -> str:
    if len(content) <= max_size:
        return content

    logger.warning(
        "Truncating %s from %d to %d bytes",
        name, len(content), max_size
    )
    return content[:max_size] + "\n... [truncated]"
```

### 5. Conventional Commit Format

**Question**: What is the exact format for conventional commits?

**Decision**: Follow standard format: `type(scope): description`

**Rationale**: Conventional Commits specification defines:
- **type**: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
- **scope**: Optional, parenthesized component name
- **description**: Imperative mood, lowercase, no period

**Examples**:
- `feat(auth): add password reset functionality`
- `fix: resolve null pointer in user service`
- `docs(readme): update installation instructions`

**Validation Regex**:
```python
CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([a-z0-9-]+\))?:\s.+$",
    re.IGNORECASE
)
```

### 6. PR Description Sections

**Question**: What sections should PR descriptions include?

**Decision**: Configurable sections with defaults: Summary, Changes, Testing

**Rationale**: Per FR-008, PRDescriptionGenerator returns markdown with configurable sections. Defaults cover essential information:
- **Summary**: Brief overview of the PR purpose
- **Changes**: What was modified and why
- **Testing**: Validation status and test coverage

**Template**:
```markdown
## Summary
{brief_description}

## Changes
{changes_list}

## Testing
{validation_status}
```

### 7. Code Analysis Types

**Question**: What analysis types should CodeAnalyzer support?

**Decision**: Three types per FR-009: explain, review, summarize

**Rationale**: These cover the primary use cases for quick code analysis:
- **explain**: Plain-English explanation of what code does
- **review**: Potential issues, improvements, observations
- **summarize**: Brief summary of purpose and structure

**System Prompts by Type**:
```python
ANALYSIS_PROMPTS = {
    "explain": "Explain what this code does in plain English...",
    "review": "Review this code for potential issues, improvements...",
    "summarize": "Provide a brief summary of this code's purpose...",
}
```

## Technology Best Practices

### Claude Agent SDK Patterns

1. **Use `query()` for stateless operations**: Generators don't need session state
2. **Set `max_turns=1`**: Prevents multi-turn conversations
3. **Empty `allowed_tools`**: Generators should not use tools
4. **Explicit `system_prompt`**: Define output format in system prompt
5. **Stream processing**: Use async for loop to handle messages

### Python Async Patterns

1. **Use `asyncio` for I/O**: All generators are async per FR-013
2. **Avoid blocking calls**: Don't use synchronous I/O in async methods
3. **Type hints everywhere**: Complete type annotations per constitution

### Testing Patterns

1. **Mock `query()` function**: Use `unittest.mock.AsyncMock`
2. **Test truncation edge cases**: Empty input, at-limit, over-limit
3. **Test prompt generation**: Verify system prompts include format requirements
4. **Test error propagation**: Verify exceptions are raised correctly

## Sources

- [Claude Agent SDK Python - GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Agent SDK Overview - Claude Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK Tutorial - DataCamp](https://www.datacamp.com/tutorial/how-to-use-claude-agent-sdk)
- [Conventional Commits](https://www.conventionalcommits.org/)
