"""Unit tests for validation utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.models.implementation import ValidationResult, ValidationStep
from maverick.utils.validation import (
    check_validation_passed,
    run_validation_pipeline,
    run_validation_step,
)


class TestRunValidationStep:
    """Tests for run_validation_step function."""

    @pytest.mark.asyncio
    async def test_run_validation_step_format_success(self) -> None:
        """Test running format validation step successfully."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.FORMAT, Path("/repo"))

        assert result.step == ValidationStep.FORMAT
        assert result.success is True
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_validation_step_lint_success(self) -> None:
        """Test running lint validation step successfully."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.LINT, Path("/repo"))

        assert result.step == ValidationStep.LINT
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_validation_step_typecheck_success(self) -> None:
        """Test running typecheck validation step successfully."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.TYPECHECK, Path("/repo"))

        assert result.step == ValidationStep.TYPECHECK
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_validation_step_test_success(self) -> None:
        """Test running test validation step successfully."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"All tests passed", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.TEST, Path("/repo"))

        assert result.step == ValidationStep.TEST
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_validation_step_failure(self) -> None:
        """Test validation step returns failure."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Error: formatting issues found")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.FORMAT, Path("/repo"))

        assert result.success is False
        assert "Error" in result.output

    @pytest.mark.asyncio
    async def test_run_validation_step_timeout(self) -> None:
        """Test validation step handles timeout."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(
                ValidationStep.TEST, Path("/repo"), timeout=1.0
            )

        assert result.success is False
        assert "timed out" in result.output.lower()

    @pytest.mark.asyncio
    async def test_run_validation_step_tool_not_found(self) -> None:
        """Test validation step handles missing tool gracefully."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=FileNotFoundError("ruff"))

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ruff")
        ):
            result = await run_validation_step(ValidationStep.FORMAT, Path("/repo"))

        # Should skip if tool not found (success=True)
        assert result.success is True
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_run_validation_step_detects_auto_fix(self) -> None:
        """Test validation step detects auto-fix in format step."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Formatted 5 files", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.FORMAT, Path("/repo"))

        assert result.success is True
        assert result.auto_fixed is True

    @pytest.mark.asyncio
    async def test_run_validation_step_detects_fixes_in_lint(self) -> None:
        """Test validation step detects fixes in lint step."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Fixed 3 issues", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.LINT, Path("/repo"))

        assert result.auto_fixed is True

    @pytest.mark.asyncio
    async def test_run_validation_step_measures_duration(self) -> None:
        """Test validation step measures execution duration."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_validation_step(ValidationStep.FORMAT, Path("/repo"))

        assert result.duration_ms >= 0


class TestRunValidationPipeline:
    """Tests for run_validation_pipeline function."""

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_all_steps_success(self) -> None:
        """Test full validation pipeline with all steps passing."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await run_validation_pipeline(Path("/repo"))

        assert len(results) == 4
        assert all(r.success for r in results)
        assert results[0].step == ValidationStep.FORMAT
        assert results[1].step == ValidationStep.LINT
        assert results[2].step == ValidationStep.TYPECHECK
        assert results[3].step == ValidationStep.TEST

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_stops_on_failure(self) -> None:
        """Test pipeline stops on first failure when stop_on_failure=True."""
        # Format passes
        mock_format_process = AsyncMock()
        mock_format_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_format_process.returncode = 0

        # Lint fails (returns 3 times for retries)
        mock_lint_process = AsyncMock()
        mock_lint_process.communicate = AsyncMock(
            return_value=(b"", b"Lint errors found")
        )
        mock_lint_process.returncode = 1

        # Format passes, then lint fails 3 times (retries)
        processes = [
            mock_format_process,
            mock_lint_process,
            mock_lint_process,
            mock_lint_process,
        ]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[min(call_count[0], len(processes) - 1)]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            results = await run_validation_pipeline(Path("/repo"), stop_on_failure=True)

        # Should stop after lint failure (after retries)
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_continues_on_failure(self) -> None:
        """Test pipeline continues on failure when stop_on_failure=False."""
        # All steps fail
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await run_validation_pipeline(
                Path("/repo"), stop_on_failure=False
            )

        assert len(results) == 4
        assert all(not r.success for r in results)

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_custom_steps(self) -> None:
        """Test pipeline runs only specified steps."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await run_validation_pipeline(
                Path("/repo"),
                steps=[ValidationStep.FORMAT, ValidationStep.LINT],
            )

        assert len(results) == 2
        assert results[0].step == ValidationStep.FORMAT
        assert results[1].step == ValidationStep.LINT

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_retries_auto_fixable_steps(self) -> None:
        """Test pipeline retries auto-fixable steps on failure."""
        # First attempt: format fails
        mock_fail_process = AsyncMock()
        mock_fail_process.communicate = AsyncMock(
            return_value=(b"", b"formatting needed")
        )
        mock_fail_process.returncode = 1

        # Second attempt: format succeeds (after auto-fix)
        mock_success_process = AsyncMock()
        mock_success_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_success_process.returncode = 0

        processes = [mock_fail_process, mock_success_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            results = await run_validation_pipeline(
                Path("/repo"),
                steps=[ValidationStep.FORMAT],
                max_retries=3,
            )

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_non_fixable_no_retry(self) -> None:
        """Test pipeline doesn't retry non-auto-fixable steps."""
        # Typecheck fails
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"type error"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            results = await run_validation_pipeline(
                Path("/repo"),
                steps=[ValidationStep.TYPECHECK],
                max_retries=3,
            )

        # Should only be called once (no retries for typecheck)
        assert mock.call_count == 1
        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_run_validation_pipeline_max_retries_respected(self) -> None:
        """Test pipeline respects max_retries limit."""
        # Always fail
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            results = await run_validation_pipeline(
                Path("/repo"),
                steps=[ValidationStep.FORMAT],
                max_retries=3,
            )

        # Should retry up to max_retries times
        assert mock.call_count == 3
        assert len(results) == 1
        assert results[0].success is False


class TestCheckValidationPassed:
    """Tests for check_validation_passed function."""

    def test_check_validation_passed_all_success(self) -> None:
        """Test returns True when all validations passed."""
        results = [
            ValidationResult(step=ValidationStep.FORMAT, success=True),
            ValidationResult(step=ValidationStep.LINT, success=True),
            ValidationResult(step=ValidationStep.TYPECHECK, success=True),
        ]

        assert check_validation_passed(results) is True

    def test_check_validation_passed_one_failure(self) -> None:
        """Test returns False when one validation failed."""
        results = [
            ValidationResult(step=ValidationStep.FORMAT, success=True),
            ValidationResult(step=ValidationStep.LINT, success=False),
            ValidationResult(step=ValidationStep.TYPECHECK, success=True),
        ]

        assert check_validation_passed(results) is False

    def test_check_validation_passed_all_failure(self) -> None:
        """Test returns False when all validations failed."""
        results = [
            ValidationResult(step=ValidationStep.FORMAT, success=False),
            ValidationResult(step=ValidationStep.LINT, success=False),
        ]

        assert check_validation_passed(results) is False

    def test_check_validation_passed_empty_list(self) -> None:
        """Test returns True for empty results list."""
        results: list[ValidationResult] = []

        # Empty list means all (zero) items are successful
        assert check_validation_passed(results) is True


class TestValidationResultCreation:
    """Tests for ValidationResult creation and properties."""

    def test_validation_result_instantiation(self) -> None:
        """Test creating a ValidationResult."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
            output="Formatted successfully",
            duration_ms=1500,
            auto_fixed=False,
        )

        assert result.step == ValidationStep.FORMAT
        assert result.success is True
        assert result.output == "Formatted successfully"
        assert result.duration_ms == 1500
        assert result.auto_fixed is False

    def test_validation_result_defaults(self) -> None:
        """Test ValidationResult uses default values."""
        result = ValidationResult(
            step=ValidationStep.LINT,
            success=False,
        )

        assert result.step == ValidationStep.LINT
        assert result.success is False
        assert result.output == ""
        assert result.duration_ms == 0
        assert result.auto_fixed is False

    def test_validation_result_frozen(self) -> None:
        """Test ValidationResult is frozen (immutable)."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        # Should not be able to modify
        with pytest.raises(Exception):  # Pydantic raises in frozen mode
            result.success = False  # type: ignore
