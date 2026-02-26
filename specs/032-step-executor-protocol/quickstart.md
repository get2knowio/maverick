# Quickstart: StepExecutor Protocol

**Branch**: `032-step-executor-protocol` | **Feature**: StepExecutor Protocol

---

## Overview

The StepExecutor protocol decouples workflow agent step execution from the Claude Agent SDK.
After this feature lands, all YAML workflow agent steps route through a `StepExecutor`
implementation rather than directly instantiating a `MaverickAgent`.

For most users, behavior is identical — the default `ClaudeStepExecutor` preserves all
existing streaming, circuit-breaker, and error-wrapping behavior. The benefit comes when
building alternative provider adapters or when you need fine-grained control over step
execution (timeouts, retries, output schema validation).

---

## Basic Usage (YAML Workflow)

Existing agent steps work unchanged:

```yaml
steps:
  - name: implement
    type: agent
    agent: implementer
    context:
      task_description: ${{ inputs.task }}
      cwd: ${{ steps.create_workspace.output.workspace_path }}
```

---

## Typed Output Contracts (P2)

Specify an `output_schema` to get validated, typed results from agent steps:

```yaml
steps:
  - name: review
    type: agent
    agent: code_reviewer
    output_schema: maverick.agents.reviewer.ReviewResult
    context:
      pr_diff: ${{ inputs.pr_diff }}
```

When `output_schema` is provided:
- The agent's raw output is validated against the Pydantic model
- `ExecutorResult.output` contains a validated `ReviewResult` instance
- Schema mismatch raises `OutputSchemaValidationError` with detailed field errors

---

## Per-Step Configuration (P3)

Configure timeout or retry behavior per step (future YAML support):

```python
# Programmatic workflow construction
from maverick.dsl.executor import StepExecutorConfig, RetryPolicy

config = StepExecutorConfig(
    timeout=600,  # 10-minute timeout for long-running implementations
    retry_policy=RetryPolicy(max_attempts=2, wait_min=5.0, wait_max=30.0),
)
```

---

## Implementing an Alternative Provider Adapter

Satisfy the `StepExecutor` protocol to support a different AI provider:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.dsl.executor import (
    ExecutorResult,
    StepExecutor,
    StepExecutorConfig,
    UsageMetadata,
)
from maverick.dsl.executor.errors import OutputSchemaValidationError
from maverick.dsl.serialization.executor.handlers.base import EventCallback


class OpenAIStepExecutor:
    """Example OpenAI provider adapter — satisfies StepExecutor protocol."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult:
        # ... call OpenAI API ...
        raw_result = await self._call_openai(
            prompt=str(prompt),
            system=instructions or "",
            tools=allowed_tools or [],
        )

        # Validate output schema if provided
        if output_schema is not None:
            from pydantic import ValidationError
            try:
                validated = output_schema.model_validate(raw_result)
                raw_result = validated
            except ValidationError as e:
                raise OutputSchemaValidationError(step_name, output_schema, e) from e

        return ExecutorResult(
            output=raw_result,
            success=True,
            usage=UsageMetadata(input_tokens=100, output_tokens=50),
            events=(),
        )


# Inject into workflow execution:
from maverick.dsl.context import WorkflowContext

context = WorkflowContext(inputs={})
context.step_executor = OpenAIStepExecutor(api_key="sk-...")
```

---

## Observability

Three structured log events are emitted per agent step execution:

```
executor.step_start
  → step_name, agent_name, config (serialized)

executor.step_complete
  → step_name, duration_ms, usage (token counts), success

executor.step_error
  → step_name, error_type, attempt_number
```

---

## Public API

```python
from maverick.dsl.executor import (
    StepExecutor,          # Protocol (runtime-checkable)
    ExecutorResult,        # Return value dataclass
    StepExecutorConfig,    # Per-step execution settings
    RetryPolicy,           # Retry parameters
    UsageMetadata,         # Token/cost metadata
    ClaudeStepExecutor,    # Claude adapter (default)
    DEFAULT_EXECUTOR_CONFIG,  # timeout=300, no overrides
)
from maverick.dsl.executor.errors import (
    ExecutorError,
    OutputSchemaValidationError,
)
```

---

## Architecture Diagram

```
WorkflowFileExecutor.execute()
    │
    ├── Creates ClaudeStepExecutor(registry) → sets context.step_executor
    │
    └── For each AGENT step:
            execute_agent_step()
                │
                ├── Builds agent context (ImplementerContext, etc.)
                │
                ├── Calls context.step_executor.execute(
                │       step_name, agent_name, prompt=context,
                │       output_schema, config, event_callback
                │   )
                │
                ├── ClaudeStepExecutor:
                │     ├── Logs executor.step_start
                │     ├── Instantiates MaverickAgent subclass
                │     ├── Injects stream_callback (→ AgentStreamChunk events)
                │     ├── Applies retry policy (if configured)
                │     ├── Calls agent.execute(prompt)
                │     ├── Validates output_schema (if provided)
                │     ├── Logs executor.step_complete
                │     └── Returns ExecutorResult
                │
                └── HandlerOutput(result=result.output, events=list(result.events))
```
