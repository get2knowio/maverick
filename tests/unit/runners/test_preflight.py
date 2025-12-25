"""Tests for preflight validation module.

Tests cover:
- ValidationResult: data model for individual validation results
- PreflightResult: aggregated results with from_results() classmethod
- PreflightConfig: configuration for validation behavior
- PreflightValidator: parallel orchestration with timeouts
- CustomToolValidator: custom tool validation from config
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import CustomToolConfig
from maverick.runners.preflight import (
    CustomToolValidator,
    PreflightConfig,
    PreflightResult,
    PreflightValidator,
    ValidationResult,
)

# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_values(self) -> None:
        """Test ValidationResult with minimal required arguments."""
        result = ValidationResult(success=True, component="TestComponent")

        assert result.success is True
        assert result.component == "TestComponent"
        assert result.errors == ()
        assert result.warnings == ()
        assert result.duration_ms == 0

    def test_with_errors(self) -> None:
        """Test ValidationResult with error messages."""
        result = ValidationResult(
            success=False,
            component="FailingComponent",
            errors=("Error 1", "Error 2"),
            duration_ms=150,
        )

        assert result.success is False
        assert result.component == "FailingComponent"
        assert result.errors == ("Error 1", "Error 2")
        assert result.warnings == ()
        assert result.duration_ms == 150

    def test_with_warnings(self) -> None:
        """Test ValidationResult with warning messages."""
        result = ValidationResult(
            success=True,
            component="WarningComponent",
            warnings=("Warning 1", "Warning 2"),
            duration_ms=50,
        )

        assert result.success is True
        assert result.warnings == ("Warning 1", "Warning 2")
        assert result.errors == ()

    def test_with_errors_and_warnings(self) -> None:
        """Test ValidationResult with both errors and warnings."""
        result = ValidationResult(
            success=False,
            component="MixedComponent",
            errors=("Critical error",),
            warnings=("Minor warning",),
            duration_ms=200,
        )

        assert result.success is False
        assert result.errors == ("Critical error",)
        assert result.warnings == ("Minor warning",)

    def test_to_dict_serialization(self) -> None:
        """Test to_dict() produces correct dictionary."""
        result = ValidationResult(
            success=False,
            component="SerializedComponent",
            errors=("err1", "err2"),
            warnings=("warn1",),
            duration_ms=123,
        )

        d = result.to_dict()

        assert d == {
            "success": False,
            "component": "SerializedComponent",
            "errors": ("err1", "err2"),
            "warnings": ("warn1",),
            "duration_ms": 123,
        }

    def test_frozen_immutability(self) -> None:
        """Test that ValidationResult is immutable (frozen dataclass)."""
        result = ValidationResult(success=True, component="Frozen")

        with pytest.raises(AttributeError):
            result.success = False


# =============================================================================
# PreflightResult Tests
# =============================================================================


class TestPreflightResult:
    """Tests for PreflightResult dataclass and from_results() classmethod."""

    def test_default_values(self) -> None:
        """Test PreflightResult with minimal required arguments."""
        result = PreflightResult(
            success=True,
            results=(),
            total_duration_ms=0,
        )

        assert result.success is True
        assert result.results == ()
        assert result.total_duration_ms == 0
        assert result.failed_components == ()
        assert result.all_errors == ()
        assert result.all_warnings == ()

    def test_from_results_all_success(self) -> None:
        """Test from_results() with all successful validations."""
        results = [
            ValidationResult(success=True, component="Git", duration_ms=50),
            ValidationResult(success=True, component="GitHub", duration_ms=100),
            ValidationResult(success=True, component="Validation", duration_ms=75),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=150)

        assert preflight.success is True
        assert len(preflight.results) == 3
        assert preflight.total_duration_ms == 150
        assert preflight.failed_components == ()
        assert preflight.all_errors == ()

    def test_from_results_all_failure(self) -> None:
        """Test from_results() with all failed validations."""
        results = [
            ValidationResult(
                success=False,
                component="Git",
                errors=("git not found",),
                duration_ms=10,
            ),
            ValidationResult(
                success=False,
                component="GitHub",
                errors=("gh not authenticated",),
                duration_ms=20,
            ),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=30)

        assert preflight.success is False
        assert preflight.failed_components == ("Git", "GitHub")
        assert len(preflight.all_errors) == 2
        assert "[Git] git not found" in preflight.all_errors
        assert "[GitHub] gh not authenticated" in preflight.all_errors

    def test_from_results_mixed_success_failure(self) -> None:
        """Test from_results() with mixed success and failure."""
        results = [
            ValidationResult(success=True, component="Git", duration_ms=50),
            ValidationResult(
                success=False,
                component="GitHub",
                errors=("auth error",),
                duration_ms=30,
            ),
            ValidationResult(success=True, component="Validation", duration_ms=40),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=100)

        assert preflight.success is False
        assert preflight.failed_components == ("GitHub",)
        assert preflight.all_errors == ("[GitHub] auth error",)

    def test_from_results_aggregates_warnings(self) -> None:
        """Test from_results() aggregates warnings from all validations."""
        results = [
            ValidationResult(
                success=True,
                component="Git",
                warnings=("git version old",),
                duration_ms=50,
            ),
            ValidationResult(
                success=True,
                component="GitHub",
                warnings=("rate limit low",),
                duration_ms=40,
            ),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=80)

        assert preflight.success is True
        assert len(preflight.all_warnings) == 2
        assert "[Git] git version old" in preflight.all_warnings
        assert "[GitHub] rate limit low" in preflight.all_warnings

    def test_from_results_multiple_errors_per_component(self) -> None:
        """Test from_results() handles multiple errors per component."""
        results = [
            ValidationResult(
                success=False,
                component="Validation",
                errors=("lint failed", "format failed", "type check failed"),
                duration_ms=100,
            ),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=100)

        assert preflight.success is False
        assert len(preflight.all_errors) == 3
        assert "[Validation] lint failed" in preflight.all_errors
        assert "[Validation] format failed" in preflight.all_errors
        assert "[Validation] type check failed" in preflight.all_errors

    def test_to_dict_serialization(self) -> None:
        """Test to_dict() produces correct dictionary structure."""
        results = [
            ValidationResult(
                success=False,
                component="Git",
                errors=("error1",),
                warnings=("warning1",),
                duration_ms=50,
            ),
        ]

        preflight = PreflightResult.from_results(results, total_duration_ms=50)
        d = preflight.to_dict()

        assert d["success"] is False
        assert d["total_duration_ms"] == 50
        assert d["failed_components"] == ["Git"]
        assert d["all_errors"] == ["[Git] error1"]
        assert d["all_warnings"] == ["[Git] warning1"]
        assert len(d["results"]) == 1
        assert d["results"][0]["component"] == "Git"

    def test_frozen_immutability(self) -> None:
        """Test that PreflightResult is immutable (frozen dataclass)."""
        preflight = PreflightResult(success=True, results=(), total_duration_ms=0)

        with pytest.raises(AttributeError):
            preflight.success = False


# =============================================================================
# PreflightConfig Tests
# =============================================================================


class TestPreflightConfig:
    """Tests for PreflightConfig dataclass."""

    def test_default_values(self) -> None:
        """Test PreflightConfig default values."""
        config = PreflightConfig()

        assert config.timeout_per_check == 5.0
        assert config.fail_on_warning is False

    def test_custom_values(self) -> None:
        """Test PreflightConfig with custom values."""
        config = PreflightConfig(timeout_per_check=10.0, fail_on_warning=True)

        assert config.timeout_per_check == 10.0
        assert config.fail_on_warning is True

    def test_partial_custom_values(self) -> None:
        """Test PreflightConfig with partially custom values."""
        config = PreflightConfig(timeout_per_check=2.5)

        assert config.timeout_per_check == 2.5
        assert config.fail_on_warning is False

    def test_frozen_immutability(self) -> None:
        """Test that PreflightConfig is immutable (frozen dataclass)."""
        config = PreflightConfig()

        with pytest.raises(AttributeError):
            config.timeout_per_check = 10.0


# =============================================================================
# PreflightValidator Tests
# =============================================================================


class TestPreflightValidator:
    """Tests for PreflightValidator orchestration."""

    @pytest.fixture
    def mock_successful_runner(self) -> MagicMock:
        """Create a mock runner that returns success."""
        runner = MagicMock()
        runner.__class__.__name__ = "MockSuccessRunner"
        runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=True,
                component="MockSuccessRunner",
                duration_ms=50,
            )
        )
        return runner

    @pytest.fixture
    def mock_failing_runner(self) -> MagicMock:
        """Create a mock runner that returns failure."""
        runner = MagicMock()
        runner.__class__.__name__ = "MockFailRunner"
        runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="MockFailRunner",
                errors=("validation failed",),
                duration_ms=30,
            )
        )
        return runner

    @pytest.fixture
    def mock_warning_runner(self) -> MagicMock:
        """Create a mock runner that returns success with warnings."""
        runner = MagicMock()
        runner.__class__.__name__ = "MockWarningRunner"
        runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=True,
                component="MockWarningRunner",
                warnings=("something is deprecated",),
                duration_ms=40,
            )
        )
        return runner

    @pytest.mark.asyncio
    async def test_run_with_no_runners(self) -> None:
        """Test run() with no runners returns empty success result."""
        validator = PreflightValidator(runners=[])

        result = await validator.run()

        assert result.success is True
        assert result.results == ()
        assert result.total_duration_ms == 0

    @pytest.mark.asyncio
    async def test_run_with_all_successful(
        self, mock_successful_runner: MagicMock
    ) -> None:
        """Test run() with all validations passing."""
        runner2 = MagicMock()
        runner2.__class__.__name__ = "MockSuccessRunner2"
        runner2.validate = AsyncMock(
            return_value=ValidationResult(
                success=True,
                component="MockSuccessRunner2",
                duration_ms=60,
            )
        )

        validator = PreflightValidator(
            runners=[mock_successful_runner, runner2],
        )

        result = await validator.run()

        assert result.success is True
        assert len(result.results) == 2
        assert result.failed_components == ()
        assert result.all_errors == ()

    @pytest.mark.asyncio
    async def test_run_with_all_failing(self, mock_failing_runner: MagicMock) -> None:
        """Test run() with all validations failing."""
        runner2 = MagicMock()
        runner2.__class__.__name__ = "MockFailRunner2"
        runner2.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="MockFailRunner2",
                errors=("another failure",),
                duration_ms=20,
            )
        )

        validator = PreflightValidator(
            runners=[mock_failing_runner, runner2],
        )

        result = await validator.run()

        assert result.success is False
        assert len(result.results) == 2
        assert len(result.failed_components) == 2

    @pytest.mark.asyncio
    async def test_run_with_mixed_success_failure(
        self, mock_successful_runner: MagicMock, mock_failing_runner: MagicMock
    ) -> None:
        """Test run() with mixed success and failure."""
        validator = PreflightValidator(
            runners=[mock_successful_runner, mock_failing_runner],
        )

        result = await validator.run()

        assert result.success is False
        assert len(result.results) == 2
        assert "MockFailRunner" in result.failed_components
        assert "MockSuccessRunner" not in result.failed_components

    @pytest.mark.asyncio
    async def test_run_with_warnings(self, mock_warning_runner: MagicMock) -> None:
        """Test run() with warnings (should still succeed)."""
        validator = PreflightValidator(runners=[mock_warning_runner])

        result = await validator.run()

        assert result.success is True
        assert len(result.all_warnings) == 1
        assert "deprecated" in result.all_warnings[0]

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Test that slow runners are timed out."""
        slow_runner = MagicMock()
        slow_runner.__class__.__name__ = "SlowRunner"

        async def slow_validate() -> ValidationResult:
            await asyncio.sleep(10)  # Much longer than timeout
            return ValidationResult(success=True, component="SlowRunner")

        slow_runner.validate = slow_validate

        config = PreflightConfig(timeout_per_check=0.1)  # 100ms timeout
        validator = PreflightValidator(runners=[slow_runner], config=config)

        result = await validator.run()

        assert result.success is False
        assert len(result.results) == 1
        assert "SlowRunner" in result.failed_components
        assert any("timed out" in err for err in result.all_errors)

    @pytest.mark.asyncio
    async def test_exception_handling_in_validate(self) -> None:
        """Test that exceptions in validate() are caught and reported."""
        error_runner = MagicMock()
        error_runner.__class__.__name__ = "ErrorRunner"
        error_runner.validate = AsyncMock(
            side_effect=RuntimeError("Something went wrong")
        )

        validator = PreflightValidator(runners=[error_runner])

        result = await validator.run()

        assert result.success is False
        assert len(result.results) == 1
        assert "ErrorRunner" in result.failed_components
        assert any("Something went wrong" in err for err in result.all_errors)

    @pytest.mark.asyncio
    async def test_parallel_execution(self) -> None:
        """Test that validations run concurrently."""
        execution_times: list[float] = []

        async def create_timed_runner(name: str, delay: float) -> MagicMock:
            runner = MagicMock()
            runner.__class__.__name__ = name

            async def timed_validate() -> ValidationResult:
                start = asyncio.get_event_loop().time()
                await asyncio.sleep(delay)
                execution_times.append(asyncio.get_event_loop().time() - start)
                return ValidationResult(success=True, component=name, duration_ms=100)

            runner.validate = timed_validate
            return runner

        # Create 3 runners each taking 0.1s
        runner1 = await create_timed_runner("Runner1", 0.1)
        runner2 = await create_timed_runner("Runner2", 0.1)
        runner3 = await create_timed_runner("Runner3", 0.1)

        validator = PreflightValidator(runners=[runner1, runner2, runner3])

        import time

        start = time.monotonic()
        result = await validator.run()
        total_time = time.monotonic() - start

        assert result.success is True
        assert len(result.results) == 3
        # If sequential, would take ~0.3s; parallel should be ~0.1s
        # Allow generous margin for CI environments
        assert total_time < 0.25, f"Expected parallel execution, took {total_time}s"

    @pytest.mark.asyncio
    async def test_custom_config_timeout(self) -> None:
        """Test that custom timeout config is used."""
        runner = MagicMock()
        runner.__class__.__name__ = "CustomTimeoutRunner"

        async def medium_validate() -> ValidationResult:
            await asyncio.sleep(0.2)  # 200ms
            return ValidationResult(success=True, component="CustomTimeoutRunner")

        runner.validate = medium_validate

        # Config with 50ms timeout - should time out
        config = PreflightConfig(timeout_per_check=0.05)
        validator = PreflightValidator(runners=[runner], config=config)

        result = await validator.run()

        assert result.success is False
        assert any("timed out" in err for err in result.all_errors)

    @pytest.mark.asyncio
    async def test_default_config_is_used(
        self, mock_successful_runner: MagicMock
    ) -> None:
        """Test that default config is used when not provided."""
        validator = PreflightValidator(runners=[mock_successful_runner])

        # Access private attribute to verify default config
        assert validator._config.timeout_per_check == 5.0
        assert validator._config.fail_on_warning is False


# =============================================================================
# CustomToolValidator Tests
# =============================================================================


class TestCustomToolValidator:
    """Tests for CustomToolValidator."""

    @pytest.mark.asyncio
    async def test_no_custom_tools(self) -> None:
        """Test validation with no custom tools configured."""
        validator = CustomToolValidator(custom_tools=[])

        result = await validator.validate()

        assert result.success is True
        assert result.component == "CustomTools"
        assert result.errors == ()
        assert result.warnings == ()

    @pytest.mark.asyncio
    async def test_existing_tool_success(self) -> None:
        """Test validation with an existing tool on PATH."""
        # Use a tool that should exist on all systems
        tool_config = CustomToolConfig(
            name="Python",
            command="python3",
            required=True,
        )

        validator = CustomToolValidator(custom_tools=[tool_config])

        with patch("shutil.which", return_value="/usr/bin/python3"):
            result = await validator.validate()

        assert result.success is True
        assert result.errors == ()
        assert result.warnings == ()

    @pytest.mark.asyncio
    async def test_missing_required_tool_error(self) -> None:
        """Test that missing required tool produces an error."""
        tool_config = CustomToolConfig(
            name="NonexistentTool",
            command="nonexistent-tool-xyz",
            required=True,
            hint="Install with: npm install -g nonexistent-tool",
        )

        validator = CustomToolValidator(custom_tools=[tool_config])

        with patch("shutil.which", return_value=None):
            result = await validator.validate()

        assert result.success is False
        assert len(result.errors) == 1
        assert "NonexistentTool" in result.errors[0]
        assert "nonexistent-tool-xyz" in result.errors[0]
        assert "Install with:" in result.errors[0]
        assert result.warnings == ()

    @pytest.mark.asyncio
    async def test_missing_optional_tool_warning(self) -> None:
        """Test that missing optional tool produces a warning, not error."""
        tool_config = CustomToolConfig(
            name="OptionalTool",
            command="optional-tool",
            required=False,
            hint="Optional: install for better experience",
        )

        validator = CustomToolValidator(custom_tools=[tool_config])

        with patch("shutil.which", return_value=None):
            result = await validator.validate()

        assert result.success is True
        assert result.errors == ()
        assert len(result.warnings) == 1
        assert "OptionalTool" in result.warnings[0]
        assert "optional-tool" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_multiple_tools_all_present(self) -> None:
        """Test validation with multiple tools all present."""
        tools = [
            CustomToolConfig(name="Tool1", command="tool1", required=True),
            CustomToolConfig(name="Tool2", command="tool2", required=True),
            CustomToolConfig(name="Tool3", command="tool3", required=False),
        ]

        validator = CustomToolValidator(custom_tools=tools)

        with patch("shutil.which", return_value="/usr/bin/tool"):
            result = await validator.validate()

        assert result.success is True
        assert result.errors == ()
        assert result.warnings == ()

    @pytest.mark.asyncio
    async def test_multiple_tools_mixed_presence(self) -> None:
        """Test validation with some tools missing."""
        tools = [
            CustomToolConfig(name="Present", command="present", required=True),
            CustomToolConfig(name="MissingReq", command="missing-req", required=True),
            CustomToolConfig(name="MissingOpt", command="missing-opt", required=False),
        ]

        validator = CustomToolValidator(custom_tools=tools)

        def which_mock(cmd: str) -> str | None:
            if cmd == "present":
                return "/usr/bin/present"
            return None

        with patch("shutil.which", side_effect=which_mock):
            result = await validator.validate()

        assert result.success is False
        assert len(result.errors) == 1
        assert "MissingReq" in result.errors[0]
        assert len(result.warnings) == 1
        assert "MissingOpt" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_tool_without_hint(self) -> None:
        """Test missing tool message without hint."""
        tool_config = CustomToolConfig(
            name="NoHintTool",
            command="no-hint",
            required=True,
            hint=None,
        )

        validator = CustomToolValidator(custom_tools=[tool_config])

        with patch("shutil.which", return_value=None):
            result = await validator.validate()

        assert result.success is False
        assert "NoHintTool" in result.errors[0]
        assert "no-hint" in result.errors[0]
        # Should end with "PATH." and not have extra hint text
        assert result.errors[0].endswith("PATH.")

    @pytest.mark.asyncio
    async def test_duration_is_recorded(self) -> None:
        """Test that validation duration is recorded."""
        validator = CustomToolValidator(custom_tools=[])

        result = await validator.validate()

        # Duration should be non-negative (could be 0 for fast execution)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_component_name_is_custom_tools(self) -> None:
        """Test that component name is always 'CustomTools'."""
        tools = [
            CustomToolConfig(name="SomeTool", command="some-tool", required=True),
        ]

        validator = CustomToolValidator(custom_tools=tools)

        with patch("shutil.which", return_value="/usr/bin/some-tool"):
            result = await validator.validate()

        assert result.component == "CustomTools"
