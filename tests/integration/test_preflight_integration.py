"""Integration tests for preflight validation system.

Tests end-to-end preflight validation with mock runners and real PreflightValidator.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import CustomToolConfig
from maverick.runners.preflight import (
    CustomToolValidator,
    PreflightConfig,
    PreflightValidator,
    ValidationResult,
)

if TYPE_CHECKING:
    from maverick.runners.protocols import ValidatableRunner


class MockRunner:
    """Mock runner that implements ValidatableRunner protocol."""

    def __init__(
        self,
        name: str,
        success: bool = True,
        errors: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        delay: float = 0.0,
    ) -> None:
        """Initialize mock runner.

        Args:
            name: Component name for this runner.
            success: Whether validation should succeed.
            errors: Error messages to return.
            warnings: Warning messages to return.
            delay: Simulated delay in seconds for validation.
        """
        self._name = name
        self._success = success
        self._errors = errors
        self._warnings = warnings
        self._delay = delay
        # Track if validate was called for testing
        self.validate_called = False
        self.validate_call_time: float | None = None

    async def validate(self) -> ValidationResult:
        """Validate this runner (mock implementation).

        Returns:
            ValidationResult with configured success/error state.
        """
        self.validate_called = True
        self.validate_call_time = time.monotonic()

        if self._delay > 0:
            await asyncio.sleep(self._delay)

        duration_ms = int(self._delay * 1000) if self._delay > 0 else 10

        return ValidationResult(
            success=self._success,
            component=self._name,
            errors=self._errors,
            warnings=self._warnings,
            duration_ms=duration_ms,
        )


class TestPreflightIntegration:
    """Integration tests for preflight validation system."""

    @pytest.mark.asyncio
    async def test_preflight_with_all_passing_runners(self) -> None:
        """Test with multiple mock runners all returning success."""
        # Create multiple mock runners that all succeed
        runners = [
            MockRunner(name="GitRunner", success=True),
            MockRunner(name="GitHubRunner", success=True),
            MockRunner(name="ValidationRunner", success=True),
        ]

        validator = PreflightValidator(
            runners=runners,
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await validator.run()

        # Verify overall success
        assert result.success is True
        assert len(result.results) == 3
        assert result.failed_components == ()
        assert result.all_errors == ()

        # Verify all runners were called
        for runner in runners:
            assert runner.validate_called is True

        # Verify each result maps to expected component
        component_names = {r.component for r in result.results}
        assert component_names == {"GitRunner", "GitHubRunner", "ValidationRunner"}

    @pytest.mark.asyncio
    async def test_preflight_with_one_failing_runner(self) -> None:
        """Test aggregation when one runner fails."""
        runners = [
            MockRunner(name="GitRunner", success=True),
            MockRunner(
                name="GitHubRunner",
                success=False,
                errors=("GitHub CLI not authenticated",),
            ),
            MockRunner(name="ValidationRunner", success=True),
        ]

        validator = PreflightValidator(
            runners=runners,
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await validator.run()

        # Verify overall failure due to one failing runner
        assert result.success is False
        assert len(result.results) == 3
        assert result.failed_components == ("GitHubRunner",)
        assert len(result.all_errors) == 1
        assert "[GitHubRunner] GitHub CLI not authenticated" in result.all_errors

        # Verify all runners were still called
        for runner in runners:
            assert runner.validate_called is True

    @pytest.mark.asyncio
    async def test_preflight_with_timeout(self) -> None:
        """Test that slow runners are timed out properly."""

        # Create typed subclass for proper class name identification on timeout
        class SlowMockRunner(MockRunner):
            """Slow runner that will timeout."""

            pass

        # Create a slow runner that exceeds timeout
        slow_runner = SlowMockRunner(
            name="SlowRunner",
            success=True,
            delay=2.0,  # 2 second delay
        )
        # Use regular MockRunner for fast runner - it returns its _name in the result
        fast_runner = MockRunner(name="FastRunner", success=True)

        validator = PreflightValidator(
            runners=[slow_runner, fast_runner],
            config=PreflightConfig(timeout_per_check=0.1),  # 100ms timeout
        )

        start_time = time.monotonic()
        result = await validator.run()
        elapsed = time.monotonic() - start_time

        # Verify timeout occurred (should complete well under 2 seconds)
        assert elapsed < 1.0, f"Expected fast timeout, but took {elapsed:.2f}s"

        # Verify overall failure due to timeout
        assert result.success is False

        # Find the slow runner's result by class name
        # When a timeout occurs, PreflightValidator uses runner.__class__.__name__
        slow_result = next(
            (r for r in result.results if r.component == "SlowMockRunner"),
            None,
        )
        assert slow_result is not None
        assert slow_result.success is False
        assert any("timed out" in err.lower() for err in slow_result.errors)

        # Fast runner should have succeeded - component comes from ValidationResult
        # which uses the name we passed to MockRunner
        fast_result = next(
            (r for r in result.results if r.component == "FastRunner"),
            None,
        )
        assert fast_result is not None
        assert fast_result.success is True

    @pytest.mark.asyncio
    async def test_preflight_with_custom_tools(self) -> None:
        """Test integration with CustomToolValidator."""
        # Create custom tool configs - one for a tool that exists, one that doesn't
        custom_tools = [
            CustomToolConfig(
                name="Python",
                command="python3",  # Should exist
                required=True,
            ),
            CustomToolConfig(
                name="NonExistentTool",
                command="nonexistent_tool_xyz_123",  # Should not exist
                required=True,
                hint="Install via: fake-package-manager install nonexistent",
            ),
        ]

        # Use patch to control shutil.which behavior
        with patch("maverick.runners.preflight.shutil.which") as mock_which:
            # python3 exists, nonexistent_tool doesn't
            mock_which.side_effect = (
                lambda cmd: "/usr/bin/python3" if cmd == "python3" else None
            )

            tool_validator = CustomToolValidator(custom_tools=custom_tools)
            result = await tool_validator.validate()

        # Should fail because nonexistent_tool is required
        assert result.success is False
        assert result.component == "CustomTools"
        assert len(result.errors) == 1
        assert "NonExistentTool" in result.errors[0]
        assert "nonexistent_tool_xyz_123" in result.errors[0]
        assert "Install via" in result.errors[0]  # Hint should be included

    @pytest.mark.asyncio
    async def test_preflight_with_custom_tools_optional(self) -> None:
        """Test CustomToolValidator with optional tools produces warnings."""
        custom_tools = [
            CustomToolConfig(
                name="OptionalTool",
                command="optional_missing_tool",
                required=False,
                hint="Optional tool hint",
            ),
        ]

        with patch("maverick.runners.preflight.shutil.which", return_value=None):
            tool_validator = CustomToolValidator(custom_tools=custom_tools)
            result = await tool_validator.validate()

        # Should succeed because tool is optional
        assert result.success is True
        assert result.component == "CustomTools"
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert "OptionalTool" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_preflight_result_aggregation(self) -> None:
        """Test that all results are properly aggregated."""
        # Create runners with various states
        runners = [
            MockRunner(
                name="SuccessWithWarning",
                success=True,
                warnings=("Deprecation warning",),
            ),
            MockRunner(
                name="FailureWithMultipleErrors",
                success=False,
                errors=("Error 1", "Error 2"),
            ),
            MockRunner(
                name="SuccessClean",
                success=True,
            ),
            MockRunner(
                name="FailureWithWarning",
                success=False,
                errors=("Critical error",),
                warnings=("Also a warning",),
            ),
        ]

        validator = PreflightValidator(
            runners=runners,
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await validator.run()

        # Verify aggregation
        assert result.success is False
        assert len(result.results) == 4

        # Verify failed components
        assert set(result.failed_components) == {
            "FailureWithMultipleErrors",
            "FailureWithWarning",
        }

        # Verify all errors are aggregated with component prefix
        assert len(result.all_errors) == 3
        error_set = set(result.all_errors)
        assert "[FailureWithMultipleErrors] Error 1" in error_set
        assert "[FailureWithMultipleErrors] Error 2" in error_set
        assert "[FailureWithWarning] Critical error" in error_set

        # Verify all warnings are aggregated with component prefix
        assert len(result.all_warnings) == 2
        warning_set = set(result.all_warnings)
        assert "[SuccessWithWarning] Deprecation warning" in warning_set
        assert "[FailureWithWarning] Also a warning" in warning_set

    @pytest.mark.asyncio
    async def test_preflight_parallel_execution(self) -> None:
        """Verify runners execute in parallel (timing test)."""
        # Create multiple runners with delays
        delay = 0.2  # 200ms each
        num_runners = 3

        runners = [
            MockRunner(name=f"SlowRunner{i}", success=True, delay=delay)
            for i in range(num_runners)
        ]

        validator = PreflightValidator(
            runners=runners,
            config=PreflightConfig(timeout_per_check=5.0),
        )

        start_time = time.monotonic()
        result = await validator.run()
        elapsed = time.monotonic() - start_time

        # Verify all succeeded
        assert result.success is True
        assert len(result.results) == num_runners

        # If sequential, would take num_runners * delay = 0.6s
        # If parallel, should take ~delay = 0.2s (plus overhead)
        # Allow some margin for test environment variability
        max_expected_time = delay * 1.5  # 0.3s with margin
        min_sequential_time = delay * num_runners * 0.8  # 0.48s minimum if sequential

        assert elapsed < min_sequential_time, (
            f"Execution took {elapsed:.3f}s, appears sequential "
            f"(expected parallel < {max_expected_time:.3f}s)"
        )

        # Verify runners started at approximately the same time
        call_times = [r.validate_call_time for r in runners if r.validate_call_time]
        if len(call_times) == num_runners:
            time_spread = max(call_times) - min(call_times)
            assert time_spread < 0.1, (
                f"Runners started {time_spread:.3f}s apart, expected parallel start"
            )

    @pytest.mark.asyncio
    async def test_preflight_with_mixed_runners_and_custom_tools(self) -> None:
        """Test integration with both regular runners and CustomToolValidator."""
        # Create regular mock runners
        runners: list[ValidatableRunner] = [
            MockRunner(name="GitRunner", success=True),
            MockRunner(
                name="GitHubRunner",
                success=False,
                errors=("Not authenticated",),
            ),
        ]

        # Create and add CustomToolValidator as a runner
        custom_tools = [
            CustomToolConfig(name="Git", command="git", required=True),
        ]

        with patch(
            "maverick.runners.preflight.shutil.which", return_value="/usr/bin/git"
        ):
            tool_validator = CustomToolValidator(custom_tools=custom_tools)
            # Add tool validator to runners list
            # type: ignore[list-item]
            all_runners = list(runners) + [tool_validator]

            validator = PreflightValidator(
                runners=all_runners,
                config=PreflightConfig(timeout_per_check=5.0),
            )

            result = await validator.run()

        # Overall should fail due to GitHubRunner
        assert result.success is False
        assert len(result.results) == 3
        assert "GitHubRunner" in result.failed_components

        # CustomToolValidator should have succeeded
        custom_result = next(
            (r for r in result.results if r.component == "CustomTools"), None
        )
        assert custom_result is not None
        assert custom_result.success is True

    @pytest.mark.asyncio
    async def test_preflight_empty_custom_tools(self) -> None:
        """Test CustomToolValidator with empty tool list."""
        tool_validator = CustomToolValidator(custom_tools=[])
        result = await tool_validator.validate()

        assert result.success is True
        assert result.component == "CustomTools"
        assert result.errors == ()
        assert result.warnings == ()

    @pytest.mark.asyncio
    async def test_preflight_exception_handling(self) -> None:
        """Test that exceptions in runners are handled gracefully."""
        # Create a runner that raises an exception
        exception_runner = MagicMock()
        exception_runner.__class__.__name__ = "ExceptionRunner"
        exception_runner.validate = AsyncMock(
            side_effect=RuntimeError("Unexpected error in validation")
        )

        normal_runner = MockRunner(name="NormalRunner", success=True)

        validator = PreflightValidator(
            runners=[exception_runner, normal_runner],
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await validator.run()

        # Should still complete and include error
        assert result.success is False
        assert len(result.results) == 2

        # Exception runner should have failed with error message
        exc_result = next(
            (r for r in result.results if r.component == "ExceptionRunner"), None
        )
        assert exc_result is not None
        assert exc_result.success is False
        assert any("error" in err.lower() for err in exc_result.errors)

        # Normal runner should still succeed
        normal_result = next(
            (r for r in result.results if r.component == "NormalRunner"), None
        )
        assert normal_result is not None
        assert normal_result.success is True
