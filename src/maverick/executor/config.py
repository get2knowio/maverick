"""StepConfig Pydantic model and RetryPolicy frozen dataclass.

StepConfig is the per-step execution configuration surface for DSL workflows.
It supersedes the old ``StepExecutorConfig`` frozen dataclass, adding richer
fields (mode, autonomy, provider, allowed_tools, prompt overrides) and
cross-field validation.

Imports ``StepMode`` and ``AutonomyLevel`` from ``maverick.types``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, Field, model_validator

from maverick.exceptions import ConfigError
from maverick.logging import get_logger
from maverick.types import AutonomyLevel, StepMode, StepType

if TYPE_CHECKING:
    from maverick.config import AgentConfig, ModelConfig

logger = get_logger(__name__)

# Canonical agent name used by the implementer step in DSL workflows.
IMPLEMENTER_AGENT_NAME = "implementer"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tenacity retry parameters for executor-level retry (FR-003).

    Maps directly to tenacity:
        stop_after_attempt(max_attempts)
        wait_exponential(multiplier=1, min=wait_min, max=wait_max)

    Attributes:
        max_attempts: Maximum number of total attempts (initial + retries).
        wait_min: Minimum wait between retries in seconds.
        wait_max: Maximum wait between retries in seconds.
    """

    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "wait_min": self.wait_min,
            "wait_max": self.wait_max,
        }


class StepConfig(BaseModel):
    """Per-step execution configuration for DSL workflows.

    All fields default to ``None``, meaning "use provider/agent defaults".
    The executor only enforces a setting when it is explicitly non-None.

    Cross-field validation rules:
        - Deterministic steps cannot set agent-only fields (autonomy beyond
          OPERATOR, allowed_tools, prompt_suffix, prompt_file).
        - ``prompt_suffix`` and ``prompt_file`` are mutually exclusive.
        - ``max_retries`` and ``retry_policy`` are mutually exclusive.

    Attributes:
        mode: Execution strategy (deterministic vs. agent).
        autonomy: Agent independence level for human-in-the-loop control.
        provider: AI provider identifier. Defaults to the configured default
            provider.
        model_id: Model identifier override (e.g. ``"claude-opus-4-6"``).
            None means inherit from the workflow or global config.
        temperature: Sampling temperature override, clamped to [0.0, 1.0].
        max_tokens: Maximum output tokens override, clamped to (0, 200000].
        timeout: Step timeout in seconds. None = provider default.
        max_retries: Maximum number of retry attempts. Mutually exclusive
            with ``retry_policy``.
        allowed_tools: Explicit tool allowlist. ``None`` means all tools are
            available; an empty list ``[]`` means no tools.
        prompt_suffix: Inline text appended to the agent's system prompt.
            Mutually exclusive with ``prompt_file``.
        prompt_file: Path to a file whose contents are appended to the
            agent's system prompt. Mutually exclusive with ``prompt_suffix``.
        retry_policy: Deprecated tenacity retry policy kept for backward
            compatibility. Prefer ``max_retries`` for new workflows.
    """

    mode: StepMode | None = None
    autonomy: AutonomyLevel | None = None
    provider: str | None = None
    model_id: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0, le=200000)
    timeout: int | None = Field(default=None, gt=0)
    max_retries: int | None = Field(default=None, ge=0)
    allowed_tools: list[str] | None = None
    prompt_suffix: str | None = None
    prompt_file: str | None = None
    retry_policy: RetryPolicy | None = None

    model_config = {"frozen": True, "arbitrary_types_allowed": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_agent_only_fields(self) -> Self:
        """Reject agent-only fields when mode is deterministic.

        Deterministic steps execute fixed logic without LLM involvement, so
        agent-specific configuration (autonomy beyond OPERATOR, tool lists,
        and prompt overrides) is nonsensical and likely a user error.

        Returns:
            The validated instance.

        Raises:
            ValueError: If agent-only fields are set on a deterministic step.
        """
        if self.mode != StepMode.DETERMINISTIC:
            return self

        errors: list[str] = []

        if self.autonomy is not None and self.autonomy != AutonomyLevel.OPERATOR:
            errors.append(
                f"autonomy={self.autonomy.value!r} is not valid for "
                f"deterministic steps (only 'operator' or None allowed)"
            )
        if self.allowed_tools is not None:
            errors.append("allowed_tools cannot be set on deterministic steps")
        if self.prompt_suffix is not None:
            errors.append("prompt_suffix cannot be set on deterministic steps")
        if self.prompt_file is not None:
            errors.append("prompt_file cannot be set on deterministic steps")

        if errors:
            raise ValueError(
                "Invalid configuration for deterministic step: " + "; ".join(errors)
            )

        return self

    @model_validator(mode="after")
    def validate_prompt_exclusivity(self) -> Self:
        """Ensure prompt_suffix and prompt_file are mutually exclusive.

        Only one prompt override mechanism may be active at a time. Setting
        both is ambiguous and rejected at validation time.

        Returns:
            The validated instance.

        Raises:
            ValueError: If both prompt_suffix and prompt_file are set.
        """
        if self.prompt_suffix is not None and self.prompt_file is not None:
            raise ValueError(
                "prompt_suffix and prompt_file are mutually exclusive; "
                "set one or the other, not both"
            )
        return self

    @model_validator(mode="after")
    def validate_retry_migration(self) -> Self:
        """Ensure max_retries and retry_policy are mutually exclusive.

        ``max_retries`` is the preferred field for new workflows.
        ``retry_policy`` is kept for backward compatibility. Setting both
        creates an ambiguous retry configuration and is rejected.

        Returns:
            The validated instance.

        Raises:
            ValueError: If both max_retries and retry_policy are set.
        """
        if self.max_retries is not None and self.retry_policy is not None:
            raise ValueError(
                "max_retries and retry_policy are mutually exclusive; "
                "use max_retries for new workflows or retry_policy for "
                "backward compatibility, not both"
            )
        return self


_MODE_OVERRIDABLE: frozenset[StepType] = frozenset({StepType.PYTHON})
"""Step types that accept an explicit mode override different from the inferred default.

Currently only ``StepType.PYTHON`` supports ``mode: agent`` to enable
mode-aware dispatch (Spec 034).
"""


def infer_step_mode(
    step_type: StepType,
    explicit_mode: StepMode | None,
) -> StepMode:
    """Infer execution mode from step type when not explicitly set.

    Maps step types to their natural execution mode:
    - agent, generate → StepMode.AGENT
    - python, validate → StepMode.DETERMINISTIC
    - subworkflow → StepMode.AGENT
    - branch, loop, checkpoint → StepMode.DETERMINISTIC

    When ``explicit_mode`` is provided, validates it is consistent with
    the step type. Step types in ``_MODE_OVERRIDABLE`` accept an explicit
    mode that differs from the inferred default (e.g. PYTHON + AGENT).

    Args:
        step_type: The step's type discriminator.
        explicit_mode: Explicitly set mode, or None for inference.

    Returns:
        The resolved StepMode.

    Raises:
        ValueError: If explicit_mode contradicts the step type and the
            step type is not in ``_MODE_OVERRIDABLE``.
    """
    _type_to_mode: dict[StepType, StepMode] = {
        StepType.AGENT: StepMode.AGENT,
        StepType.GENERATE: StepMode.AGENT,
        StepType.PYTHON: StepMode.DETERMINISTIC,
        StepType.VALIDATE: StepMode.DETERMINISTIC,
        StepType.SUBWORKFLOW: StepMode.AGENT,
        StepType.BRANCH: StepMode.DETERMINISTIC,
        StepType.LOOP: StepMode.DETERMINISTIC,
        StepType.CHECKPOINT: StepMode.DETERMINISTIC,
    }

    inferred = _type_to_mode[step_type]

    if explicit_mode is None:
        return inferred

    if explicit_mode != inferred:
        if step_type in _MODE_OVERRIDABLE:
            return explicit_mode
        raise ValueError(
            f"mode={explicit_mode.value!r} is incompatible with "
            f"step type={step_type.value!r} (expected {inferred.value!r})"
        )

    return explicit_mode


def resolve_step_config(
    *,
    inline_config: dict[str, Any] | None,
    project_step_config: StepConfig | None,
    agent_config: AgentConfig | None,
    global_model: ModelConfig,
    step_type: StepType,
    step_name: str,
    provider_default_model: str | None = None,
) -> StepConfig:
    """Resolve per-step configuration from 5-layer precedence.

    Resolution order (highest to lowest priority):
    1. ``inline_config``: Raw dict from workflow YAML step's ``config`` field.
    2. ``project_step_config``: From ``MaverickConfig.steps[step_name]``.
    3. ``agent_config``: From ``MaverickConfig.agents[agent_name]``.
    4. ``global_model``: From ``MaverickConfig.model``.
    5. ``provider_default_model``: From ``AgentProviderConfig.default_model``.

    Mode is inferred from ``step_type`` when not explicitly set by any layer.
    Autonomy defaults to ``AutonomyLevel.OPERATOR`` when not set.
    Provider is ``None`` when not set, allowing the executor to resolve via
    the registry's default provider.

    Args:
        inline_config: Raw YAML config dict from step record.
        project_step_config: Project-level step default.
        agent_config: Agent-level model overrides.
        global_model: Global model configuration.
        step_type: The step's type (for mode inference).
        step_name: Step name (for error messages).
        provider_default_model: Default model from the ACP provider config
            (lowest precedence layer).

    Returns:
        Fully-resolved StepConfig with no None model fields.

    Raises:
        ConfigError: If mode/step_type mismatch or invalid field combinations.
    """
    # --- Step 1: Parse inline_config dict to StepConfig ---
    parsed_inline: StepConfig | None = None
    if inline_config:
        # Handle legacy "model" key → "model_id" rename
        coerced = dict(inline_config)
        if "model" in coerced and "model_id" not in coerced:
            coerced["model_id"] = coerced.pop("model")
            logger.warning(
                "legacy_model_key_renamed",
                step_name=step_name,
                message=(
                    "Renamed 'model' to 'model_id' in inline config. "
                    "Update your workflow YAML to use 'model_id' directly."
                ),
            )
        elif "model" in coerced and "model_id" in coerced:
            # Both keys present — drop legacy key, warn
            coerced.pop("model")
            logger.warning(
                "duplicate_model_keys",
                step_name=step_name,
                message=(
                    "Both 'model' and 'model_id' found in inline config; "
                    "using 'model_id'. Remove the deprecated 'model' key."
                ),
            )

        try:
            parsed_inline = StepConfig.model_validate(coerced)
        except Exception as exc:
            raise ConfigError(
                f"Invalid inline config for step '{step_name}': {exc}"
            ) from exc

    # --- Step 2: Resolve model fields via 4-layer precedence ---
    # For model_id, temperature, max_tokens: first non-None from
    # inline → project → agent → global
    def _first_non_none(*values: Any) -> Any:
        """Return the first non-None value, or None if all are None."""
        for v in values:
            if v is not None:
                return v
        return None

    model_id = _first_non_none(
        parsed_inline.model_id if parsed_inline else None,
        project_step_config.model_id if project_step_config else None,
        agent_config.model_id if agent_config else None,
        global_model.model_id,
        provider_default_model,
    )

    temperature = _first_non_none(
        parsed_inline.temperature if parsed_inline else None,
        project_step_config.temperature if project_step_config else None,
        agent_config.temperature if agent_config else None,
        global_model.temperature,
    )

    max_tokens = _first_non_none(
        parsed_inline.max_tokens if parsed_inline else None,
        project_step_config.max_tokens if project_step_config else None,
        agent_config.max_tokens if agent_config else None,
        global_model.max_tokens,
    )

    # --- Step 3: Resolve provider (None → executor resolves via registry default) ---
    provider = _first_non_none(
        parsed_inline.provider if parsed_inline else None,
        project_step_config.provider if project_step_config else None,
    )

    # --- Step 4: Resolve mode via infer_step_mode ---
    explicit_mode = _first_non_none(
        parsed_inline.mode if parsed_inline else None,
        project_step_config.mode if project_step_config else None,
    )
    try:
        mode = infer_step_mode(step_type, explicit_mode)
    except ValueError as exc:
        raise ConfigError(f"Mode/type mismatch for step '{step_name}': {exc}") from exc

    # --- Step 5: Resolve autonomy (default OPERATOR) ---
    autonomy = _first_non_none(
        parsed_inline.autonomy if parsed_inline else None,
        project_step_config.autonomy if project_step_config else None,
    )
    if autonomy is None:
        autonomy = AutonomyLevel.OPERATOR

    # --- Step 6: Resolve remaining fields (simple precedence) ---
    timeout = _first_non_none(
        parsed_inline.timeout if parsed_inline else None,
        project_step_config.timeout if project_step_config else None,
    )

    max_retries = _first_non_none(
        parsed_inline.max_retries if parsed_inline else None,
        project_step_config.max_retries if project_step_config else None,
    )

    allowed_tools = _first_non_none(
        parsed_inline.allowed_tools if parsed_inline else None,
        project_step_config.allowed_tools if project_step_config else None,
    )

    prompt_suffix = _first_non_none(
        parsed_inline.prompt_suffix if parsed_inline else None,
        project_step_config.prompt_suffix if project_step_config else None,
    )

    prompt_file = _first_non_none(
        parsed_inline.prompt_file if parsed_inline else None,
        project_step_config.prompt_file if project_step_config else None,
    )

    retry_policy = _first_non_none(
        parsed_inline.retry_policy if parsed_inline else None,
        project_step_config.retry_policy if project_step_config else None,
    )

    # --- Step 7: Build and validate resolved StepConfig ---
    try:
        return StepConfig(
            mode=mode,
            autonomy=autonomy,
            provider=provider,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            allowed_tools=allowed_tools,
            prompt_suffix=prompt_suffix,
            prompt_file=prompt_file,
            retry_policy=retry_policy,
        )
    except Exception as exc:
        raise ConfigError(
            f"Invalid resolved config for step '{step_name}': {exc}"
        ) from exc


# Backward-compatible alias for code that still references the old name.
StepExecutorConfig = StepConfig

DEFAULT_EXECUTOR_CONFIG = StepConfig(timeout=300)
"""Default executor config: 300s timeout, no model/retry overrides."""
