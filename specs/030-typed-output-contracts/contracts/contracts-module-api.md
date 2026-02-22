# Contracts Module API

**Module**: `maverick.agents.contracts`
**File**: `src/maverick/agents/contracts.py`

This module serves as the centralized registry for all agent output types and the validation utility.

## Public API

### Type Re-exports

```python
from maverick.agents.contracts import (
    # Review domain (Pydantic models)
    ReviewFinding,         # from maverick.models.review
    ReviewResult,          # from maverick.models.review
    Finding,               # from maverick.models.review_models (converted)
    FindingGroup,          # from maverick.models.review_models (converted)
    GroupedReviewResult,   # from maverick.models.review_models (converted, renamed)
    FixOutcome,            # from maverick.models.review_models (converted)

    # Fixer domain
    FixerResult,           # from maverick.models.fixer (NEW)
    FixResult,             # from maverick.models.issue_fix

    # Implementation domain
    ImplementationResult,  # from maverick.models.implementation

    # Deprecated
    AgentResult,           # from maverick.agents.result (frozen dc, deprecated)

    # Utility
    validate_output,       # JSON extraction + Pydantic validation
    OutputValidationError, # Error type for validation failures
)
```

### validate_output()

```python
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

def validate_output(
    raw: str,
    model: type[T],
    *,
    strict: bool = True,
) -> T | None:
    """Extract JSON from markdown code blocks and validate against a Pydantic model.

    Args:
        raw: Raw text output from an agent, potentially containing markdown.
        model: The Pydantic BaseModel subclass to validate against.
        strict: If True (default), raise OutputValidationError on failure.
                If False, return None on failure.

    Returns:
        Validated model instance, or None if strict=False and validation fails.

    Raises:
        OutputValidationError: When strict=True and extraction/parsing/validation fails.

    Example:
        result = validate_output(agent_text, FixerResult)
        # result is a validated FixerResult instance
    """
```

### OutputValidationError

```python
class OutputValidationError(MaverickError):
    """Raised when agent output cannot be parsed into the expected model.

    Attributes:
        expected_model: Name of the expected Pydantic model class.
        raw_output: The raw text that failed (truncated to 500 chars).
        parse_error: What went wrong.
        stage: Where in the pipeline it failed.
    """
    expected_model: str
    raw_output: str
    parse_error: str
    stage: Literal["extraction", "json_parse", "validation"]
```

## SDK Structured Output Integration

### MaverickAgent._build_options() Extension

```python
# In base.py _build_options():
def _build_options(self, cwd: str | Path | None = None) -> Any:
    options = ClaudeAgentOptions(
        # ... existing fields ...
        output_format=self._output_format,  # NEW: optional structured output
    )
    return options
```

### Agent-Level Usage Pattern

```python
class FixerAgent(MaverickAgent[AgentContext, FixerResult]):
    def __init__(self):
        super().__init__(
            name="fixer",
            instructions="...",
            allowed_tools=[...],
            output_model=FixerResult,  # NEW: triggers SDK structured output
        )

    async def execute(self, context: AgentContext) -> FixerResult:
        messages = []
        async for msg in self.query(prompt, cwd=context.cwd):
            messages.append(msg)

        # SDK structured output path
        structured = self._extract_structured_output(messages)
        if structured is not None:
            return FixerResult.model_validate(structured)

        # Fallback: validate_output from raw text
        raw_text = extract_all_text(messages)
        return validate_output(raw_text, FixerResult)
```

## Module Layout

```python
# src/maverick/agents/contracts.py

"""Centralized agent output contract registry.

All agent output types are re-exported from this module for single-import access.
Use validate_output() to parse and validate raw agent text against a contract.

Example:
    from maverick.agents.contracts import FixerResult, validate_output

    result = validate_output(raw_text, FixerResult)
"""

from __future__ import annotations

__all__ = [
    # Review domain
    "ReviewFinding",
    "ReviewResult",
    "Finding",
    "FindingGroup",
    "GroupedReviewResult",
    "FixOutcome",
    # Fixer domain
    "FixerResult",
    "FixResult",
    # Implementation domain
    "ImplementationResult",
    # Deprecated
    "AgentResult",
    # Utility
    "validate_output",
    "OutputValidationError",
]
```
