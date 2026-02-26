# Structured Output Integration Contract

**Module**: `maverick.agents.base`
**Integration**: Claude Agent SDK `output_format` parameter

## MaverickAgent Base Class Changes

### New Constructor Parameter

```python
class MaverickAgent(ABC, Generic[TContext, TResult]):
    def __init__(
        self,
        name: str,
        instructions: str,
        allowed_tools: list[str],
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int | None = None,
        temperature: float | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        output_model: type[BaseModel] | None = None,  # NEW
    ):
        self._output_model = output_model
        self._output_format = (
            {
                "type": "json_schema",
                "schema": output_model.model_json_schema(),
            }
            if output_model is not None
            else None
        )
```

### _build_options() Extension

```python
def _build_options(self, cwd: str | Path | None = None) -> Any:
    return ClaudeAgentOptions(
        allowed_tools=self._allowed_tools,
        system_prompt={...},
        # ... existing fields ...
        output_format=self._output_format,  # NEW
    )
```

### New Helper: _extract_structured_output()

```python
def _extract_structured_output(
    self,
    messages: list[Any],
) -> dict[str, Any] | None:
    """Extract structured output from SDK ResultMessage.

    Searches messages for a ResultMessage with structured_output populated.
    Returns the raw dict for caller to validate via model_validate().

    Args:
        messages: List of SDK messages from query() or client interaction.

    Returns:
        Parsed dict from structured_output, or None if not found.
    """
    from claude_agent_sdk import ResultMessage

    for msg in reversed(messages):
        if isinstance(msg, ResultMessage) and msg.structured_output is not None:
            return msg.structured_output
    return None
```

## Per-Agent Output Flow

```
Agent.__init__(output_model=FixerResult)
    │
    ▼
_build_options() includes output_format with JSON schema
    │
    ▼
SDK enforces schema on agent's final output
    │
    ▼
ResultMessage.structured_output = validated dict
    │
    ▼
Agent.execute():
    structured = _extract_structured_output(messages)
    if structured:
        return FixerResult.model_validate(structured)
    else:
        # Fallback for edge cases
        return validate_output(extract_all_text(messages), FixerResult)
```

## Error Handling

| SDK Error Subtype | Maverick Mapping | Action |
|-------------------|------------------|--------|
| `"error_max_structured_output_retries"` | `MalformedResponseError` | Log structured output failure, attempt `validate_output()` fallback |
| `"success"` + no `structured_output` | N/A | Use `validate_output()` fallback |
| Pydantic `ValidationError` on `model_validate()` | `OutputValidationError` | Wrap and raise with context |
