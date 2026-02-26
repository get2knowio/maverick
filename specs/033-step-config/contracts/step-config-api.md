# API Contract: Step Configuration Model

**Feature**: 033-step-config | **Date**: 2026-02-25

## StepMode Enum

**Module**: `maverick.dsl.types`

```python
class StepMode(str, Enum):
    DETERMINISTIC = "deterministic"
    AGENT = "agent"
```

## AutonomyLevel Enum

**Module**: `maverick.dsl.types`

```python
class AutonomyLevel(str, Enum):
    OPERATOR = "operator"
    COLLABORATOR = "collaborator"
    CONSULTANT = "consultant"
    APPROVER = "approver"
```

## StepConfig Model

**Module**: `maverick.dsl.executor.config`

```python
class StepConfig(BaseModel):
    """Per-step execution configuration (FR-003).

    Replaces and extends StepExecutorConfig. All fields default to None,
    meaning 'use resolved defaults from project/agent/global config'.
    """

    mode: StepMode | None = Field(
        default=None,
        description="Execution strategy. Inferred from step type when None.",
    )
    autonomy: AutonomyLevel | None = Field(
        default=None,
        description="Agent independence level. Defaults to operator when resolved.",
    )
    provider: Literal["claude"] | None = Field(
        default=None,
        description="AI provider. Only 'claude' supported.",
    )
    model_id: str | None = Field(
        default=None,
        description="Model identifier override.",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Sampling temperature override.",
    )
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        le=200000,
        description="Max output tokens override.",
    )
    timeout: int | None = Field(
        default=None,
        gt=0,
        description="Timeout in seconds.",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        description="Maximum retry attempts.",
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description="Tool whitelist. None=all tools, []=no tools.",
    )
    prompt_suffix: str | None = Field(
        default=None,
        description="Inline prompt extension appended to agent instructions.",
    )
    prompt_file: str | None = Field(
        default=None,
        description="Path to prompt file (relative to workflow file directory).",
    )
    retry_policy: RetryPolicy | None = Field(
        default=None,
        description="Deprecated. Preserved for backward compat with StepExecutorConfig.",
    )

    # --- Validators ---

    @model_validator(mode="after")
    def validate_agent_only_fields(self) -> Self:
        """Reject agent-only fields when mode is deterministic."""
        ...

    @model_validator(mode="after")
    def validate_prompt_exclusivity(self) -> Self:
        """Reject simultaneous prompt_suffix and prompt_file."""
        ...
```

## resolve_step_config Function

**Module**: `maverick.dsl.executor.config`

```python
def resolve_step_config(
    *,
    inline_config: dict[str, Any] | None,
    project_step_config: StepConfig | None,
    agent_config: AgentConfig | None,
    global_model: ModelConfig,
    step_type: StepType,
    step_name: str,
) -> StepConfig:
    """Resolve per-step configuration from 4-layer precedence.

    Resolution order (highest to lowest priority):
    1. inline_config: Raw dict from workflow YAML step's `config` field
    2. project_step_config: From MaverickConfig.steps[step_name]
    3. agent_config: From MaverickConfig.agents[agent_name]
    4. global_model: From MaverickConfig.model

    Mode is inferred from step_type when not explicitly set.
    Autonomy defaults to AutonomyLevel.OPERATOR when not set.

    Args:
        inline_config: Raw YAML config dict from step record.
        project_step_config: Project-level step default.
        agent_config: Agent-level model overrides.
        global_model: Global model configuration.
        step_type: The step's type (for mode inference).
        step_name: Step name (for error messages).

    Returns:
        Fully-resolved StepConfig with no None model fields.

    Raises:
        ConfigError: If mode/step_type mismatch or invalid field combinations.
    """
    ...
```

## StepRecord Base Class Update

**Module**: `maverick.dsl.serialization.schema`

```python
class StepRecord(BaseModel):
    name: str = Field(...)
    type: StepType
    when: str | None = None
    requires: list[str] = Field(default_factory=list)
    config: dict[str, Any] | None = Field(
        default=None,
        description="Per-step configuration overrides. Deserialized to StepConfig at execution time.",
    )
```

## AgentStepRecord Backward Compatibility

**Module**: `maverick.dsl.serialization.schema`

```python
class AgentStepRecord(StepRecord):
    type: Literal[StepType.AGENT] = StepType.AGENT
    agent: str = Field(...)
    context: dict[str, Any] | str = Field(default_factory=dict)
    rollback: str | None = None
    output_schema: str | None = None
    # executor_config removed from schema; handled by model_validator

    @model_validator(mode="before")
    @classmethod
    def migrate_executor_config(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Map legacy executor_config to config with deprecation warning."""
        ...
```

## MaverickConfig.steps Field

**Module**: `maverick.config`

```python
class MaverickConfig(BaseSettings):
    # ... existing fields ...
    steps: dict[str, StepConfig] = Field(
        default_factory=dict,
        description="Project-level step configuration defaults keyed by step name.",
    )
```

## StepExecutor Protocol Update

**Module**: `maverick.dsl.executor.protocol`

```python
@runtime_checkable
class StepExecutor(Protocol):
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
        config: StepConfig | None = None,  # Changed from StepExecutorConfig
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult:
        ...
```

## Backward Compatibility Aliases

**Module**: `maverick.dsl.executor.config`

```python
# Deprecated alias — will be removed in a future release
StepExecutorConfig = StepConfig
```
