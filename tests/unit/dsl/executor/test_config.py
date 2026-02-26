"""Tests for RetryPolicy, StepConfig, StepExecutorConfig, DEFAULT_EXECUTOR_CONFIG."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from pydantic import ValidationError as PydanticValidationError

from maverick.config import AgentConfig, ModelConfig
from maverick.dsl.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    RetryPolicy,
    StepConfig,
    StepExecutorConfig,
    infer_step_mode,
    resolve_step_config,
)
from maverick.dsl.types import AutonomyLevel, StepMode, StepType
from maverick.exceptions import ConfigError


class TestRetryPolicy:
    """Tests for RetryPolicy frozen dataclass."""

    def test_default_values(self) -> None:
        """RetryPolicy has correct defaults."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.wait_min == 1.0
        assert policy.wait_max == 10.0

    def test_custom_values(self) -> None:
        """RetryPolicy accepts custom values."""
        policy = RetryPolicy(max_attempts=5, wait_min=0.5, wait_max=30.0)
        assert policy.max_attempts == 5
        assert policy.wait_min == 0.5
        assert policy.wait_max == 30.0

    def test_to_dict_roundtrip(self) -> None:
        """RetryPolicy.to_dict() produces JSON-compatible dict."""
        policy = RetryPolicy(max_attempts=5, wait_min=2.0, wait_max=20.0)
        d = policy.to_dict()
        assert d == {"max_attempts": 5, "wait_min": 2.0, "wait_max": 20.0}

    def test_to_dict_default(self) -> None:
        """RetryPolicy.to_dict() works with defaults."""
        policy = RetryPolicy()
        d = policy.to_dict()
        assert d["max_attempts"] == 3
        assert d["wait_min"] == 1.0
        assert d["wait_max"] == 10.0

    def test_frozen_immutable(self) -> None:
        """RetryPolicy is frozen (cannot be mutated)."""
        policy = RetryPolicy()
        with pytest.raises((AttributeError, TypeError)):
            policy.max_attempts = 10  # type: ignore[misc]


class TestStepExecutorConfig:
    """Tests for StepExecutorConfig (alias for StepConfig)."""

    def test_all_none_defaults(self) -> None:
        """StepExecutorConfig defaults all fields to None."""
        config = StepExecutorConfig()
        assert config.mode is None
        assert config.autonomy is None
        assert config.provider is None
        assert config.model_id is None
        assert config.temperature is None
        assert config.max_tokens is None
        assert config.timeout is None
        assert config.max_retries is None
        assert config.allowed_tools is None
        assert config.prompt_suffix is None
        assert config.prompt_file is None
        assert config.retry_policy is None

    def test_partial_config(self) -> None:
        """StepExecutorConfig accepts partial configuration."""
        config = StepExecutorConfig(timeout=60, model_id="claude-opus-4-6")
        assert config.timeout == 60
        assert config.model_id == "claude-opus-4-6"
        assert config.retry_policy is None
        assert config.temperature is None

    def test_model_dump_all_none(self) -> None:
        """model_dump(exclude_none=True) returns empty dict when all None."""
        config = StepExecutorConfig()
        d = config.model_dump(exclude_none=True)
        assert d == {}

    def test_model_dump_with_retry_policy(self) -> None:
        """model_dump(exclude_none=True) includes nested RetryPolicy."""
        policy = RetryPolicy(max_attempts=5)
        config = StepExecutorConfig(timeout=300, retry_policy=policy)
        d = config.model_dump(exclude_none=True)
        assert d["timeout"] == 300
        assert d["retry_policy"] == {
            "max_attempts": 5,
            "wait_min": 1.0,
            "wait_max": 10.0,
        }

    def test_model_dump_full_config(self) -> None:
        """model_dump(exclude_none=True) roundtrip with all executor fields."""
        config = StepExecutorConfig(
            timeout=600,
            retry_policy=RetryPolicy(max_attempts=2),
            model_id="claude-opus-4-6",
            temperature=0.5,
            max_tokens=4096,
        )
        d = config.model_dump(exclude_none=True)
        assert d["timeout"] == 600
        assert d["model_id"] == "claude-opus-4-6"
        assert d["temperature"] == 0.5
        assert d["max_tokens"] == 4096

    def test_frozen_immutable(self) -> None:
        """StepExecutorConfig is frozen (cannot be mutated)."""
        config = StepExecutorConfig()
        with pytest.raises(PydanticValidationError):
            config.timeout = 300  # type: ignore[misc]


class TestStepConfig:
    """Tests for StepConfig Pydantic model."""

    def test_construction_with_defaults(self) -> None:
        """StepConfig() has all None fields."""
        config = StepConfig()
        assert config.mode is None
        assert config.autonomy is None
        assert config.provider is None
        assert config.model_id is None
        assert config.temperature is None
        assert config.max_tokens is None
        assert config.timeout is None
        assert config.max_retries is None
        assert config.allowed_tools is None
        assert config.prompt_suffix is None
        assert config.prompt_file is None
        assert config.retry_policy is None

    def test_construction_with_all_fields(self) -> None:
        """StepConfig accepts all fields together (agent mode)."""
        config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.CONSULTANT,
            provider="claude",
            model_id="claude-opus-4-6",
            temperature=0.7,
            max_tokens=4096,
            timeout=600,
            max_retries=3,
            allowed_tools=["Read", "Glob"],
            prompt_suffix="Focus on security",
        )
        assert config.mode == StepMode.AGENT
        assert config.autonomy == AutonomyLevel.CONSULTANT
        assert config.provider == "claude"
        assert config.model_id == "claude-opus-4-6"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.timeout == 600
        assert config.max_retries == 3
        assert config.allowed_tools == ["Read", "Glob"]
        assert config.prompt_suffix == "Focus on security"

    # --- Temperature validation ---

    def test_temperature_lower_bound(self) -> None:
        """temperature=0.0 is accepted."""
        config = StepConfig(temperature=0.0)
        assert config.temperature == 0.0

    def test_temperature_upper_bound(self) -> None:
        """temperature=1.0 is accepted."""
        config = StepConfig(temperature=1.0)
        assert config.temperature == 1.0

    def test_temperature_below_range_rejected(self) -> None:
        """temperature=-0.1 is rejected."""
        with pytest.raises(Exception):
            StepConfig(temperature=-0.1)

    def test_temperature_above_range_rejected(self) -> None:
        """temperature=1.1 is rejected."""
        with pytest.raises(Exception):
            StepConfig(temperature=1.1)

    # --- max_tokens validation ---

    def test_max_tokens_valid(self) -> None:
        """max_tokens=100 is accepted."""
        config = StepConfig(max_tokens=100)
        assert config.max_tokens == 100

    def test_max_tokens_upper_bound(self) -> None:
        """max_tokens=200000 is accepted."""
        config = StepConfig(max_tokens=200000)
        assert config.max_tokens == 200000

    def test_max_tokens_zero_rejected(self) -> None:
        """max_tokens=0 is rejected (must be > 0)."""
        with pytest.raises(Exception):
            StepConfig(max_tokens=0)

    def test_max_tokens_above_limit_rejected(self) -> None:
        """max_tokens=200001 is rejected (must be <= 200000)."""
        with pytest.raises(Exception):
            StepConfig(max_tokens=200001)

    # --- timeout validation ---

    def test_timeout_valid(self) -> None:
        """timeout=300 is accepted."""
        config = StepConfig(timeout=300)
        assert config.timeout == 300

    def test_timeout_zero_rejected(self) -> None:
        """timeout=0 is rejected (must be > 0)."""
        with pytest.raises(Exception):
            StepConfig(timeout=0)

    # --- max_retries validation ---

    def test_max_retries_zero_valid(self) -> None:
        """max_retries=0 is accepted (no retries)."""
        config = StepConfig(max_retries=0)
        assert config.max_retries == 0

    def test_max_retries_negative_rejected(self) -> None:
        """max_retries=-1 is rejected (must be >= 0)."""
        with pytest.raises(Exception):
            StepConfig(max_retries=-1)

    # --- provider validation ---

    def test_provider_claude_valid(self) -> None:
        """provider='claude' is accepted."""
        config = StepConfig(provider="claude")
        assert config.provider == "claude"

    def test_provider_invalid_rejected(self) -> None:
        """provider='openai' is rejected (only 'claude' allowed)."""
        with pytest.raises(Exception):
            StepConfig(provider="openai")

    # --- Cross-field: deterministic mode rejects agent-only fields ---

    def test_deterministic_rejects_autonomy_above_operator(self) -> None:
        """Deterministic mode rejects autonomy higher than OPERATOR."""
        with pytest.raises(Exception, match="autonomy"):
            StepConfig(mode=StepMode.DETERMINISTIC, autonomy=AutonomyLevel.CONSULTANT)

    def test_deterministic_accepts_operator_autonomy(self) -> None:
        """Deterministic mode accepts OPERATOR autonomy level."""
        config = StepConfig(
            mode=StepMode.DETERMINISTIC, autonomy=AutonomyLevel.OPERATOR
        )
        assert config.mode == StepMode.DETERMINISTIC
        assert config.autonomy == AutonomyLevel.OPERATOR

    def test_deterministic_accepts_none_autonomy(self) -> None:
        """Deterministic mode accepts None autonomy (inherit default)."""
        config = StepConfig(mode=StepMode.DETERMINISTIC)
        assert config.autonomy is None

    def test_deterministic_rejects_allowed_tools(self) -> None:
        """Deterministic mode rejects allowed_tools."""
        with pytest.raises(Exception, match="allowed_tools"):
            StepConfig(mode=StepMode.DETERMINISTIC, allowed_tools=["Read"])

    def test_deterministic_rejects_prompt_suffix(self) -> None:
        """Deterministic mode rejects prompt_suffix."""
        with pytest.raises(Exception, match="prompt_suffix"):
            StepConfig(mode=StepMode.DETERMINISTIC, prompt_suffix="extra")

    def test_deterministic_rejects_prompt_file(self) -> None:
        """Deterministic mode rejects prompt_file."""
        with pytest.raises(Exception, match="prompt_file"):
            StepConfig(mode=StepMode.DETERMINISTIC, prompt_file="path.md")

    # --- Cross-field: prompt exclusivity ---

    def test_prompt_suffix_and_file_mutually_exclusive(self) -> None:
        """Setting both prompt_suffix and prompt_file is rejected."""
        with pytest.raises(Exception, match="mutually exclusive"):
            StepConfig(prompt_suffix="inline", prompt_file="file.md")

    def test_prompt_suffix_alone_valid(self) -> None:
        """prompt_suffix alone is accepted."""
        config = StepConfig(prompt_suffix="Focus on security")
        assert config.prompt_suffix == "Focus on security"

    def test_prompt_file_alone_valid(self) -> None:
        """prompt_file alone is accepted."""
        config = StepConfig(prompt_file="prompts/review.md")
        assert config.prompt_file == "prompts/review.md"

    # --- Cross-field: retry migration ---

    def test_max_retries_and_retry_policy_mutually_exclusive(self) -> None:
        """Setting both max_retries and retry_policy is rejected."""
        with pytest.raises(Exception, match="mutually exclusive"):
            StepConfig(max_retries=3, retry_policy=RetryPolicy(max_attempts=5))

    def test_max_retries_alone_valid(self) -> None:
        """max_retries alone is accepted."""
        config = StepConfig(max_retries=3)
        assert config.max_retries == 3

    def test_retry_policy_alone_valid(self) -> None:
        """retry_policy alone is accepted."""
        policy = RetryPolicy(max_attempts=5)
        config = StepConfig(retry_policy=policy)
        assert config.retry_policy == policy

    # --- Serialization ---

    def test_model_dump_exclude_none(self) -> None:
        """model_dump(exclude_none=True) returns only set fields."""
        config = StepConfig(timeout=300, model_id="claude-opus-4-6")
        d = config.model_dump(exclude_none=True)
        assert d == {"timeout": 300, "model_id": "claude-opus-4-6"}

    def test_model_dump_empty_when_all_none(self) -> None:
        """model_dump(exclude_none=True) returns empty dict when all None."""
        config = StepConfig()
        d = config.model_dump(exclude_none=True)
        assert d == {}

    def test_yaml_round_trip(self) -> None:
        """StepConfig survives YAML dump -> load round-trip."""
        original = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.CONSULTANT,
            provider="claude",
            model_id="claude-opus-4-6",
            temperature=0.7,
            max_tokens=4096,
            timeout=600,
            max_retries=3,
            allowed_tools=["Read", "Glob"],
            prompt_suffix="Focus on security",
        )

        yaml_str = yaml.dump(original.model_dump(mode="json", exclude_none=True))
        loaded = StepConfig.model_validate(yaml.safe_load(yaml_str))

        assert loaded == original

    # --- Alias identity ---

    def test_step_executor_config_alias_identity(self) -> None:
        """StepExecutorConfig is the same class as StepConfig."""
        assert StepExecutorConfig is StepConfig

    # --- allowed_tools semantics ---

    def test_allowed_tools_none_means_all(self) -> None:
        """allowed_tools=None means all tools are available."""
        config = StepConfig(allowed_tools=None)
        assert config.allowed_tools is None

    def test_allowed_tools_empty_means_none_allowed(self) -> None:
        """allowed_tools=[] means no tools are available."""
        config = StepConfig(allowed_tools=[])
        assert config.allowed_tools == []


class TestDefaultExecutorConfig:
    """Tests for DEFAULT_EXECUTOR_CONFIG module constant."""

    def test_timeout_300(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has timeout=300."""
        assert DEFAULT_EXECUTOR_CONFIG.timeout == 300

    def test_no_retry_policy(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has no retry policy."""
        assert DEFAULT_EXECUTOR_CONFIG.retry_policy is None

    def test_no_model_override(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has no model_id override."""
        assert DEFAULT_EXECUTOR_CONFIG.model_id is None

    def test_is_step_executor_config(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG is a StepExecutorConfig instance."""
        assert isinstance(DEFAULT_EXECUTOR_CONFIG, StepExecutorConfig)

    def test_is_step_config(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG is a StepConfig instance."""
        assert isinstance(DEFAULT_EXECUTOR_CONFIG, StepConfig)


class TestInferStepMode:
    """Tests for infer_step_mode helper function."""

    # Inference from step type (explicit_mode=None)
    def test_infer_agent_step_type(self):
        assert infer_step_mode(StepType.AGENT, None) == StepMode.AGENT

    def test_infer_generate_step_type(self):
        assert infer_step_mode(StepType.GENERATE, None) == StepMode.AGENT

    def test_infer_python_step_type(self):
        assert infer_step_mode(StepType.PYTHON, None) == StepMode.DETERMINISTIC

    def test_infer_validate_step_type(self):
        assert infer_step_mode(StepType.VALIDATE, None) == StepMode.DETERMINISTIC

    def test_infer_subworkflow_step_type(self):
        assert infer_step_mode(StepType.SUBWORKFLOW, None) == StepMode.AGENT

    def test_infer_branch_step_type(self):
        assert infer_step_mode(StepType.BRANCH, None) == StepMode.DETERMINISTIC

    def test_infer_loop_step_type(self):
        assert infer_step_mode(StepType.LOOP, None) == StepMode.DETERMINISTIC

    def test_infer_checkpoint_step_type(self):
        assert infer_step_mode(StepType.CHECKPOINT, None) == StepMode.DETERMINISTIC

    # Explicit mode matching inferred
    def test_explicit_agent_on_agent_step(self):
        assert infer_step_mode(StepType.AGENT, StepMode.AGENT) == StepMode.AGENT

    def test_explicit_deterministic_on_python_step(self):
        assert (
            infer_step_mode(StepType.PYTHON, StepMode.DETERMINISTIC)
            == StepMode.DETERMINISTIC
        )

    # Mode/type mismatch rejection
    def test_mismatch_deterministic_on_agent_step(self):
        with pytest.raises(ValueError, match="incompatible"):
            infer_step_mode(StepType.AGENT, StepMode.DETERMINISTIC)

    def test_mismatch_agent_on_python_step(self):
        with pytest.raises(ValueError, match="incompatible"):
            infer_step_mode(StepType.PYTHON, StepMode.AGENT)

    def test_mismatch_agent_on_validate_step(self):
        with pytest.raises(ValueError, match="incompatible"):
            infer_step_mode(StepType.VALIDATE, StepMode.AGENT)

    def test_mismatch_deterministic_on_generate_step(self):
        with pytest.raises(ValueError, match="incompatible"):
            infer_step_mode(StepType.GENERATE, StepMode.DETERMINISTIC)

    def test_mismatch_deterministic_on_subworkflow_step(self):
        with pytest.raises(ValueError, match="incompatible"):
            infer_step_mode(StepType.SUBWORKFLOW, StepMode.DETERMINISTIC)

    # All 8 step types covered
    def test_all_step_types_have_mapping(self):
        for step_type in StepType:
            result = infer_step_mode(step_type, None)
            assert isinstance(result, StepMode)


class TestResolveStepConfig:
    """Tests for resolve_step_config 4-layer precedence resolution."""

    def _make_global(self, **kwargs: Any) -> ModelConfig:
        return ModelConfig(**kwargs)

    def _make_agent(self, **kwargs: Any) -> AgentConfig:
        return AgentConfig(**kwargs)

    def test_inline_wins_over_project(self) -> None:
        """Inline config takes precedence over project step config."""
        result = resolve_step_config(
            inline_config={"temperature": 0.7},
            project_step_config=StepConfig(temperature=0.3),
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.temperature == 0.7

    def test_project_wins_over_agent(self) -> None:
        """Project step config takes precedence over agent config."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=StepConfig(model_id="project-model"),
            agent_config=self._make_agent(model_id="agent-model"),
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.model_id == "project-model"

    def test_agent_wins_over_global(self) -> None:
        """Agent config takes precedence over global model."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=self._make_agent(model_id="agent-model"),
            global_model=self._make_global(model_id="global-model"),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.model_id == "agent-model"

    def test_global_used_when_no_overrides(self) -> None:
        """Global model config used when no layers override."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(model_id="global-model", temperature=0.5),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.model_id == "global-model"
        assert result.temperature == 0.5

    def test_model_field_inheritance_unset_fields(self) -> None:
        """Unset model fields inherited from global (SC-004)."""
        result = resolve_step_config(
            inline_config={"temperature": 0.7},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(model_id="global-model", max_tokens=8000),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.temperature == 0.7  # from inline
        assert result.model_id == "global-model"  # inherited from global
        assert result.max_tokens == 8000  # inherited from global

    def test_provider_defaults_to_claude(self) -> None:
        """Provider defaults to 'claude' when not set."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.provider == "claude"

    def test_mode_inference_integration(self) -> None:
        """Mode is inferred from step type when not explicitly set."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.PYTHON,
            step_name="test",
        )
        assert result.mode == StepMode.DETERMINISTIC

    def test_mode_inference_agent_type(self) -> None:
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.mode == StepMode.AGENT

    def test_autonomy_defaults_to_operator(self) -> None:
        """Autonomy defaults to OPERATOR when not set."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.autonomy == AutonomyLevel.OPERATOR

    def test_legacy_model_key_renamed(self) -> None:
        """Legacy 'model' key in inline_config renamed to 'model_id'."""
        result = resolve_step_config(
            inline_config={"model": "claude-opus-4-6"},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.model_id == "claude-opus-4-6"

    def test_all_four_layers_complete(self) -> None:
        """Full 4-layer resolution with all layers providing different values."""
        result = resolve_step_config(
            inline_config={"temperature": 0.9},
            project_step_config=StepConfig(model_id="project-model", timeout=300),
            agent_config=self._make_agent(model_id="agent-model", max_tokens=2000),
            global_model=self._make_global(
                model_id="global-model", max_tokens=4000, temperature=0.1
            ),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.temperature == 0.9  # inline
        assert result.model_id == "project-model"  # project (beats agent)
        assert result.max_tokens == 2000  # agent (project max_tokens was None)
        assert result.timeout == 300  # project

    def test_invalid_inline_config_raises_config_error(self) -> None:
        """Invalid inline config dict raises ConfigError."""
        with pytest.raises(ConfigError):
            resolve_step_config(
                inline_config={"temperature": 5.0},  # out of range
                project_step_config=None,
                agent_config=None,
                global_model=self._make_global(),
                step_type=StepType.AGENT,
                step_name="test",
            )

    # --- T014: Timeout and max_retries resolution ---

    def test_timeout_from_inline(self):
        """Timeout resolves from inline config."""
        result = resolve_step_config(
            inline_config={"timeout": 600},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.timeout == 600

    def test_timeout_from_project(self):
        """Timeout falls back to project step config."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=StepConfig(timeout=300),
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.timeout == 300

    def test_timeout_none_when_not_set(self):
        """Timeout is None when no layer sets it."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.timeout is None

    def test_max_retries_from_inline(self):
        """max_retries resolves from inline config."""
        result = resolve_step_config(
            inline_config={"max_retries": 3},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.max_retries == 3

    def test_max_retries_from_project(self):
        """max_retries falls back to project step config."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=StepConfig(max_retries=5),
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.max_retries == 5

    def test_max_retries_none_when_not_set(self):
        """max_retries is None when no layer sets it."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.max_retries is None

    # --- T015: Allowed tools resolution ---

    def test_allowed_tools_from_inline(self):
        """allowed_tools resolves from inline config."""
        result = resolve_step_config(
            inline_config={"allowed_tools": ["Read", "Glob", "Grep"]},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.allowed_tools == ["Read", "Glob", "Grep"]

    def test_allowed_tools_none_means_all(self):
        """None means all tools allowed (default)."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.allowed_tools is None

    def test_allowed_tools_empty_list_means_no_tools(self):
        """Empty list means no tools allowed."""
        result = resolve_step_config(
            inline_config={"allowed_tools": []},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.allowed_tools == []

    def test_allowed_tools_rejected_on_deterministic(self):
        """allowed_tools rejected when resolved mode is deterministic."""
        with pytest.raises(Exception):
            resolve_step_config(
                inline_config={"allowed_tools": ["Read"]},
                project_step_config=None,
                agent_config=None,
                global_model=self._make_global(),
                step_type=StepType.PYTHON,
                step_name="test",
            )

    def test_allowed_tools_from_project(self):
        """allowed_tools falls back to project step config."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=StepConfig(allowed_tools=["Read"]),
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.allowed_tools == ["Read"]

    # --- T016: Prompt extension resolution ---

    def test_prompt_suffix_from_inline(self):
        """prompt_suffix resolves from inline config."""
        result = resolve_step_config(
            inline_config={"prompt_suffix": "Focus on security"},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.prompt_suffix == "Focus on security"

    def test_prompt_file_from_inline(self):
        """prompt_file resolves from inline config."""
        result = resolve_step_config(
            inline_config={"prompt_file": "./prompts/review.md"},
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.prompt_file == "./prompts/review.md"

    def test_prompt_suffix_from_project(self):
        """prompt_suffix falls back to project step config."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=StepConfig(prompt_suffix="Be concise"),
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.prompt_suffix == "Be concise"

    def test_neither_prompt_set(self):
        """Neither prompt_suffix nor prompt_file when not set."""
        result = resolve_step_config(
            inline_config=None,
            project_step_config=None,
            agent_config=None,
            global_model=self._make_global(),
            step_type=StepType.AGENT,
            step_name="test",
        )
        assert result.prompt_suffix is None
        assert result.prompt_file is None
