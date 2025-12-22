from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.hooks.config import (
    HookConfig,
    LoggingConfig,
    MetricsConfig,
    SafetyConfig,
)


class TestSafetyConfig:
    """Tests for SafetyConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = SafetyConfig()
        assert config.bash_validation_enabled is True
        assert config.file_write_validation_enabled is True
        assert config.bash_blocklist == []
        assert config.bash_allow_override == []
        assert ".env" in config.sensitive_paths
        assert "~/.ssh/" in config.sensitive_paths
        assert config.fail_closed is True
        assert config.hook_timeout_seconds == 10

    def test_custom_blocklist(self) -> None:
        """Test custom bash blocklist."""
        config = SafetyConfig(bash_blocklist=["curl.*evil"])
        assert "curl.*evil" in config.bash_blocklist

    def test_invalid_regex_in_blocklist(self) -> None:
        """Test that invalid regex patterns are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SafetyConfig(bash_blocklist=["[invalid"])
        assert "Invalid regex pattern" in str(exc_info.value)

    def test_invalid_regex_in_allow_override(self) -> None:
        """Test that invalid regex patterns are rejected in allow_override."""
        with pytest.raises(ValidationError) as exc_info:
            SafetyConfig(bash_allow_override=["(unclosed"])
        assert "Invalid regex pattern" in str(exc_info.value)

    def test_timeout_bounds(self) -> None:
        """Test hook timeout validation."""
        config = SafetyConfig(hook_timeout_seconds=1)
        assert config.hook_timeout_seconds == 1

        config = SafetyConfig(hook_timeout_seconds=120)
        assert config.hook_timeout_seconds == 120

        with pytest.raises(ValidationError):
            SafetyConfig(hook_timeout_seconds=0)

        with pytest.raises(ValidationError):
            SafetyConfig(hook_timeout_seconds=121)


class TestLoggingConfig:
    """Tests for LoggingConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = LoggingConfig()
        assert config.enabled is True
        assert config.log_level == "INFO"
        assert config.output_destination == "maverick.hooks"
        assert config.sanitize_inputs is True
        assert config.max_output_length == 1000

    def test_log_level_validation(self) -> None:
        """Test log level validation."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            config = LoggingConfig(log_level=level)
            assert config.log_level == level

        with pytest.raises(ValidationError):
            LoggingConfig(log_level="INVALID")

    def test_max_output_length_bounds(self) -> None:
        """Test output length bounds."""
        config = LoggingConfig(max_output_length=100)
        assert config.max_output_length == 100

        config = LoggingConfig(max_output_length=10000)
        assert config.max_output_length == 10000

        with pytest.raises(ValidationError):
            LoggingConfig(max_output_length=99)

        with pytest.raises(ValidationError):
            LoggingConfig(max_output_length=10001)


class TestMetricsConfig:
    """Tests for MetricsConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = MetricsConfig()
        assert config.enabled is True
        assert config.max_entries == 10000
        assert config.time_window_seconds is None

    def test_max_entries_bounds(self) -> None:
        """Test max entries bounds."""
        config = MetricsConfig(max_entries=100)
        assert config.max_entries == 100

        config = MetricsConfig(max_entries=1000000)
        assert config.max_entries == 1000000

        with pytest.raises(ValidationError):
            MetricsConfig(max_entries=99)

        with pytest.raises(ValidationError):
            MetricsConfig(max_entries=1000001)

    def test_time_window(self) -> None:
        """Test time window validation."""
        config = MetricsConfig(time_window_seconds=60)
        assert config.time_window_seconds == 60

        config = MetricsConfig(time_window_seconds=3600)
        assert config.time_window_seconds == 3600

        with pytest.raises(ValidationError):
            MetricsConfig(time_window_seconds=59)


class TestHookConfig:
    """Tests for HookConfig root model."""

    def test_defaults(self) -> None:
        """Test default nested configs."""
        config = HookConfig()
        assert isinstance(config.safety, SafetyConfig)
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.metrics, MetricsConfig)

    def test_custom_nested_config(self) -> None:
        """Test custom nested configuration."""
        config = HookConfig(
            safety=SafetyConfig(bash_validation_enabled=False),
            logging=LoggingConfig(log_level="DEBUG"),
            metrics=MetricsConfig(max_entries=5000),
        )
        assert config.safety.bash_validation_enabled is False
        assert config.logging.log_level == "DEBUG"
        assert config.metrics.max_entries == 5000

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            HookConfig(unknown_field="value")  # type: ignore[call-arg]


# Factory function tests (T056-T059)


class TestCreateSafetyHooks:
    """Tests for create_safety_hooks factory function."""

    def test_returns_hook_matchers(self) -> None:
        """Test that factory returns list of HookMatcher objects."""
        from maverick.hooks import create_safety_hooks

        hooks = create_safety_hooks()
        assert isinstance(hooks, list)
        # Should return hooks for Bash and Write/Edit
        assert len(hooks) == 2

    def test_uses_default_config_when_none(self) -> None:
        """Test secure defaults when no config provided."""
        from maverick.hooks import create_safety_hooks

        hooks = create_safety_hooks(None)
        assert isinstance(hooks, list)
        assert len(hooks) == 2  # Both validations enabled by default

    def test_respects_bash_validation_disabled(self) -> None:
        """Test bash validation can be disabled."""
        from maverick.hooks import create_safety_hooks

        config = HookConfig(safety=SafetyConfig(bash_validation_enabled=False))
        hooks = create_safety_hooks(config)
        # Should only have file write hook
        assert len(hooks) == 1

    def test_respects_file_write_validation_disabled(self) -> None:
        """Test file write validation can be disabled."""
        from maverick.hooks import create_safety_hooks

        config = HookConfig(safety=SafetyConfig(file_write_validation_enabled=False))
        hooks = create_safety_hooks(config)
        # Should only have bash hook
        assert len(hooks) == 1

    def test_returns_empty_when_all_disabled(self) -> None:
        """Test returns empty list when all validation disabled."""
        from maverick.hooks import create_safety_hooks

        config = HookConfig(
            safety=SafetyConfig(
                bash_validation_enabled=False,
                file_write_validation_enabled=False,
            )
        )
        hooks = create_safety_hooks(config)
        assert hooks == []

    def test_hook_matcher_has_correct_timeout(self) -> None:
        """Test HookMatcher uses timeout from config."""
        from maverick.hooks import create_safety_hooks

        config = HookConfig(safety=SafetyConfig(hook_timeout_seconds=30))
        hooks = create_safety_hooks(config)
        # All hooks should have the configured timeout
        for hook in hooks:
            assert hook.timeout == 30

    def test_bash_hook_matcher_pattern(self) -> None:
        """Test bash hook has correct matcher pattern."""
        from maverick.hooks import create_safety_hooks

        hooks = create_safety_hooks()
        # Find the bash hook (should match "Bash")
        bash_hooks = [h for h in hooks if h.matcher == "Bash"]
        assert len(bash_hooks) == 1
        assert bash_hooks[0].matcher == "Bash"

    def test_file_write_hook_matcher_pattern(self) -> None:
        """Test file write hook has correct matcher pattern."""
        from maverick.hooks import create_safety_hooks

        hooks = create_safety_hooks()
        # Find the file write hook (should match "Write" or "Edit")
        write_hooks = [
            h
            for h in hooks
            if h.matcher and ("Write" in h.matcher or "Edit" in h.matcher)
        ]
        assert len(write_hooks) == 1


class TestCreateLoggingHooks:
    """Tests for create_logging_hooks factory function."""

    def test_returns_hook_matchers(self) -> None:
        """Test that factory returns list of HookMatcher objects."""
        from maverick.hooks import create_logging_hooks

        hooks = create_logging_hooks()
        assert isinstance(hooks, list)

    def test_uses_default_config_when_none(self) -> None:
        """Test defaults when no config provided."""
        from maverick.hooks import create_logging_hooks

        hooks = create_logging_hooks(None, None)
        assert isinstance(hooks, list)
        # Should have hooks for logging and metrics by default
        assert len(hooks) >= 1

    def test_creates_metrics_collector_when_none(self) -> None:
        """Test creates internal MetricsCollector when not provided."""
        from maverick.hooks import create_logging_hooks

        hooks = create_logging_hooks()
        # Should succeed without error
        assert isinstance(hooks, list)

    def test_uses_provided_metrics_collector(self) -> None:
        """Test uses provided metrics collector."""
        from maverick.hooks import MetricsCollector, create_logging_hooks

        collector = MetricsCollector()
        hooks = create_logging_hooks(metrics_collector=collector)
        assert isinstance(hooks, list)

    def test_respects_logging_disabled(self) -> None:
        """Test logging can be disabled."""
        from maverick.hooks import create_logging_hooks

        config = HookConfig(
            logging=LoggingConfig(enabled=False),
            metrics=MetricsConfig(enabled=False),
        )
        hooks = create_logging_hooks(config)
        assert hooks == []

    def test_respects_metrics_disabled(self) -> None:
        """Test metrics can be disabled independently."""
        from maverick.hooks import create_logging_hooks

        config = HookConfig(
            logging=LoggingConfig(enabled=True),
            metrics=MetricsConfig(enabled=False),
        )
        hooks = create_logging_hooks(config)
        # Should still have logging hook
        assert len(hooks) >= 1

    def test_hook_matcher_for_all_tools(self) -> None:
        """Test HookMatcher matches all tools (matcher=None)."""
        from maverick.hooks import create_logging_hooks

        hooks = create_logging_hooks()
        # All logging hooks should match all tools
        for hook in hooks:
            assert hook.matcher is None

    def test_returns_empty_when_all_disabled(self) -> None:
        """Test returns empty list when all logging disabled."""
        from maverick.hooks import create_logging_hooks

        config = HookConfig(
            logging=LoggingConfig(enabled=False),
            metrics=MetricsConfig(enabled=False),
        )
        hooks = create_logging_hooks(config)
        assert hooks == []
