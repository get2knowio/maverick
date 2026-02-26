# Quickstart: Typed Agent Output Contracts

**Feature Branch**: `030-typed-output-contracts`

## For Agent Authors

### Creating a New Agent with Typed Output

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.contracts import validate_output
from maverick.agents.result import AgentResult
from maverick.agents.utils import extract_all_text


class MyResult(BaseModel):
    """Output contract for MyAgent."""

    success: bool = Field(description="Whether the operation succeeded")
    summary: str = Field(description="Human-readable summary")
    items: list[str] = Field(default_factory=list, description="Items processed")


class MyAgent(MaverickAgent[AgentContext, MyResult]):
    def __init__(self) -> None:
        super().__init__(
            name="my-agent",
            instructions="You process items and return structured results.",
            allowed_tools=["Read", "Write"],
            output_model=MyResult,  # Enables SDK structured output
        )

    async def execute(self, context: AgentContext) -> MyResult:
        messages = []
        async for msg in self.query("Process these items...", cwd=context.cwd):
            messages.append(msg)

        # Try SDK structured output first
        structured = self._extract_structured_output(messages)
        if structured is not None:
            return MyResult.model_validate(structured)

        # Fallback to code-block extraction
        raw_text = extract_all_text(messages)
        return validate_output(raw_text, MyResult)
```

### Registering in the Contracts Module

Add your type to `src/maverick/agents/contracts.py`:

```python
from maverick.models.my_module import MyResult

__all__ = [
    # ... existing exports ...
    "MyResult",
]
```

## For Workflow Authors

### Consuming Typed Agent Output

```python
from maverick.agents.contracts import FixerResult

# In a workflow action:
agent = FixerAgent()
result: FixerResult = await agent.execute(context)

# Access typed fields — no string parsing needed
if result.success:
    logger.info("fix_applied", files=result.files_mentioned, summary=result.summary)
else:
    logger.error("fix_failed", error=result.error_details)
```

### Validating Raw Output (Transition Period)

```python
from maverick.agents.contracts import validate_output, FixerResult, OutputValidationError

try:
    result = validate_output(raw_agent_text, FixerResult)
except OutputValidationError as e:
    logger.error(
        "output_validation_failed",
        model=e.expected_model,
        stage=e.stage,
        error=e.parse_error,
    )
```

## Migration Checklist

For each agent being migrated:

1. Define Pydantic output model (or convert existing frozen dataclass)
2. Add `output_model=MyModel` to agent constructor
3. Update `execute()` to use `_extract_structured_output()` + `validate_output()` fallback
4. Register model in `maverick.agents.contracts`
5. Update downstream consumers to use typed fields
6. Remove regex-based extraction code
7. Add/update tests for typed output
