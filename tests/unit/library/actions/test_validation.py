"""Unit tests for validation actions.

Tests the validation.py action module including:
- run_fix_retry_loop with fix-and-retry behavior
- Exponential backoff between attempts
- Graceful error handling
- Recording of fix attempts
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maverick.library.actions.validation import (
    _build_fix_prompt,
    _summarize_errors,
    run_fix_retry_loop,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def create_validation_result(
    success: bool,
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a mock validation result for testing.

    Args:
        success: Whether validation passed
        stages: Optional list of stage results

    Returns:
        Validation result dict
    """
    if stages is None:
        stages = [
            {
                "stage": "lint",
                "success": success,
                "output": "" if success else "E501: line too long",
                "duration_ms": 100,
                "error": None if success else "E501: line too long",
            }
        ]
    return {
        "success": success,
        "stages": stages,
        "total_duration_ms": 100,
    }


def create_fix_result(
    success: bool,
    changes_made: str = "Fix applied",
    error: str | None = None,
) -> dict[str, Any]:
    """Create a mock fix result for testing.

    Args:
        success: Whether fix succeeded
        changes_made: Description of changes if successful
        error: Error message if failed

    Returns:
        Fix result dict
    """
    if success:
        return {
            "success": True,
            "changes_made": changes_made,
        }
    return {
        "success": False,
        "error": error or "Fix failed",
    }


# =============================================================================
# Test Classes
# =============================================================================


class TestRunFixRetryLoopImmediatePass:
    """Tests for when initial validation passes immediately."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_passes_immediately_when_validation_succeeds(
        self,
    ) -> None:
        """If initial validation passed, return immediately with no attempts."""
        validation_result = create_validation_result(success=True)

        result = await run_fix_retry_loop(
            stages=["lint"],
            max_attempts=3,
            fixer_agent="fixer",
            validation_result=validation_result,
        )

        assert result["passed"] is True
        assert result["attempts"] == 0
        assert result["fixes_applied"] == []
        assert result["final_result"] == validation_result


class TestRunFixRetryLoopSkipped:
    """Tests for when fix retry loop is skipped."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_skipped_when_max_attempts_zero(self) -> None:
        """If max_attempts is 0, don't retry."""
        validation_result = create_validation_result(success=False)

        result = await run_fix_retry_loop(
            stages=["lint"],
            max_attempts=0,
            fixer_agent="fixer",
            validation_result=validation_result,
        )

        assert result["passed"] is False
        assert result["attempts"] == 0
        assert result["fixes_applied"] == []
        assert result["final_result"] == validation_result

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_skipped_when_max_attempts_negative(self) -> None:
        """If max_attempts is negative, treat it as 0 and don't retry."""
        validation_result = create_validation_result(success=False)

        result = await run_fix_retry_loop(
            stages=["lint"],
            max_attempts=-1,
            fixer_agent="fixer",
            validation_result=validation_result,
        )

        assert result["passed"] is False
        assert result["attempts"] == 0
        assert result["fixes_applied"] == []


class TestRunFixRetryLoopInvokesFixer:
    """Tests for fixer agent invocation."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_invokes_fixer_agent_on_failure(self) -> None:
        """Actually invokes the fixer agent when validation fails."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
                cwd="/tmp/test",
            )

            # Verify fixer agent was called
            mock_fixer.assert_called_once()
            call_kwargs = mock_fixer.call_args.kwargs
            assert "fix_prompt" in call_kwargs
            assert call_kwargs["cwd"] == Path("/tmp/test")


class TestRunFixRetryLoopRerunsValidation:
    """Tests for validation re-run after fix attempts."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_reruns_validation_after_fix(self) -> None:
        """Re-runs validation after fix attempt."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)

            await run_fix_retry_loop(
                stages=["lint", "test"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
                cwd="/tmp/test",
            )

            # Verify validation was re-run after fix
            mock_validation.assert_called_once()
            call_kwargs = mock_validation.call_args.kwargs
            assert call_kwargs["stages"] == ["lint", "test"]
            assert call_kwargs["cwd"] == Path("/tmp/test")

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_succeeds_after_fix(self) -> None:
        """Validation passes after fix is applied."""
        initial_result = create_validation_result(success=False)
        fixed_result = create_validation_result(success=True)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            mock_fixer.return_value = create_fix_result(
                success=True, changes_made="Fixed lint error"
            )
            mock_validation.return_value = fixed_result

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            assert result["passed"] is True
            assert result["attempts"] == 1
            assert "Fixed lint error" in result["fixes_applied"]
            assert result["final_result"]["success"] is True


class TestRunFixRetryLoopMaxAttempts:
    """Tests for max attempts behavior."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_exhausts_max_attempts(self) -> None:
        """Continues until max_attempts exhausted."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep") as mock_sleep,
        ):
            # Fixer always succeeds but validation always fails
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=False)
            mock_sleep.return_value = None

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Verify all attempts were made
            assert result["passed"] is False
            assert result["attempts"] == 3
            assert mock_fixer.call_count == 3
            assert mock_validation.call_count == 3

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_stops_early_on_success(self) -> None:
        """Stops retrying when validation passes."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep"),
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            # Fail first, then succeed
            mock_validation.side_effect = [
                create_validation_result(success=False),
                create_validation_result(success=True),
            ]

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=5,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Stopped after 2 attempts because validation passed
            assert result["passed"] is True
            assert result["attempts"] == 2
            assert mock_fixer.call_count == 2


class TestRunFixRetryLoopErrorHandling:
    """Tests for error handling and graceful failure."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_handles_fixer_agent_error_gracefully(
        self,
    ) -> None:
        """Agent error doesn't crash workflow."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep"),
        ):
            # First attempt: fixer returns error (but doesn't raise exception)
            # Second attempt: fixer succeeds, validation passes
            mock_fixer.side_effect = [
                create_fix_result(success=False, error="API rate limit exceeded"),
                create_fix_result(success=True, changes_made="Applied fix"),
            ]
            mock_validation.side_effect = [
                create_validation_result(success=False),  # After failed fix
                create_validation_result(success=True),  # After successful fix
            ]

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Should have continued after first failure
            assert result["passed"] is True
            assert result["attempts"] == 2
            assert mock_fixer.call_count == 2
            # First fix attempt should be recorded as failed
            assert "failed" in result["fixes_applied"][0].lower()
            assert "API rate limit exceeded" in result["fixes_applied"][0]

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_handles_exception_gracefully(self) -> None:
        """Exception during fix doesn't crash workflow."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep"),
        ):
            # First attempt raises exception, second succeeds
            mock_fixer.side_effect = [
                RuntimeError("Network connection lost"),
                create_fix_result(success=True),
            ]
            mock_validation.return_value = create_validation_result(success=True)

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Should continue after exception
            assert result["passed"] is True
            assert result["attempts"] == 2
            # Exception should be recorded in fixes_applied
            assert "Network connection lost" in result["fixes_applied"][0]

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_continues_after_all_attempts_fail(self) -> None:
        """All attempts failing still returns gracefully."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep"),
        ):
            # All fix attempts fail with exceptions
            mock_fixer.side_effect = [
                RuntimeError("Error 1"),
                RuntimeError("Error 2"),
                RuntimeError("Error 3"),
            ]
            # Validation is not called when exceptions occur in _invoke_fixer_agent
            # because the exception is caught in the try block before validation runs
            mock_validation.return_value = create_validation_result(success=False)

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Should return gracefully
            assert result["passed"] is False
            assert result["attempts"] == 3
            assert len(result["fixes_applied"]) == 3
            for fix in result["fixes_applied"]:
                assert "failed" in fix.lower()


class TestRunFixRetryLoopExponentialBackoff:
    """Tests for exponential backoff behavior."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_applies_exponential_backoff(self) -> None:
        """Verify backoff is applied between attempts."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep") as mock_sleep,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=False)
            mock_sleep.return_value = None

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=4,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Backoff should be called for attempts 2, 3, 4 (not first attempt)
            # Base backoff is 1.0 seconds
            # Attempt 2: 1.0 * 2^(2-2) = 1.0s
            # Attempt 3: 1.0 * 2^(3-2) = 2.0s
            # Attempt 4: 1.0 * 2^(4-2) = 4.0s
            assert mock_sleep.call_count == 3
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert sleep_calls == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_no_backoff_on_first_attempt(self) -> None:
        """No backoff before first attempt."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep") as mock_sleep,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)
            mock_sleep.return_value = None

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Only one attempt needed, no backoff
            mock_sleep.assert_not_called()


class TestRunFixRetryLoopRecordsAttempts:
    """Tests for recording fix attempts."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_records_all_fix_attempts(self) -> None:
        """Records all fix attempts in fixes_applied list."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep"),
        ):
            mock_fixer.side_effect = [
                create_fix_result(success=True, changes_made="Fixed issue A"),
                create_fix_result(success=False, error="Could not fix issue B"),
                create_fix_result(success=True, changes_made="Fixed issue C"),
            ]
            mock_validation.return_value = create_validation_result(success=False)

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            assert result["attempts"] == 3
            assert len(result["fixes_applied"]) == 3
            assert "Fixed issue A" in result["fixes_applied"][0]
            assert "Could not fix issue B" in result["fixes_applied"][1]
            assert "Fixed issue C" in result["fixes_applied"][2]

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_records_default_description_when_missing(
        self,
    ) -> None:
        """Uses default description when changes_made not provided."""
        validation_result = create_validation_result(
            success=False,
            stages=[
                {
                    "stage": "lint",
                    "success": False,
                    "error": "E501: line too long",
                },
                {
                    "stage": "test",
                    "success": False,
                    "error": "AssertionError",
                },
            ],
        )

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            # Return success without changes_made field
            mock_fixer.return_value = {"success": True}
            mock_validation.return_value = create_validation_result(success=True)

            result = await run_fix_retry_loop(
                stages=["lint", "test"],
                max_attempts=1,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Should have a default description mentioning the stages
            assert len(result["fixes_applied"]) == 1
            assert "Applied fix for" in result["fixes_applied"][0]


class TestRunFixRetryLoopWorkingDirectory:
    """Tests for working directory handling."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_uses_provided_cwd(self) -> None:
        """Uses provided cwd for fixer and validation."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=1,
                fixer_agent="fixer",
                validation_result=validation_result,
                cwd="/custom/path",
            )

            mock_fixer.assert_called_once()
            mock_validation.assert_called_once()
            assert mock_fixer.call_args.kwargs["cwd"] == Path("/custom/path")
            assert mock_validation.call_args.kwargs["cwd"] == Path("/custom/path")

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_uses_current_dir_when_cwd_none(self) -> None:
        """Uses Path.cwd() when cwd is None."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.Path") as mock_path,
        ):
            mock_cwd = MagicMock()
            mock_path.cwd.return_value = mock_cwd
            mock_path.return_value = mock_cwd  # For Path(cwd) when cwd is provided
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=1,
                fixer_agent="fixer",
                validation_result=validation_result,
                cwd=None,
            )

            mock_path.cwd.assert_called_once()


class TestBuildFixPrompt:
    """Tests for _build_fix_prompt helper function."""

    def test_build_fix_prompt_includes_attempt_number(self) -> None:
        """Prompt includes current attempt number."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(result, ["lint"], attempt_number=2)

        assert "Attempt 2" in prompt

    def test_build_fix_prompt_includes_stages(self) -> None:
        """Prompt includes validation stages."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(
            result, ["lint", "test", "typecheck"], attempt_number=1
        )

        assert "lint" in prompt
        assert "test" in prompt
        assert "typecheck" in prompt

    def test_build_fix_prompt_includes_errors(self) -> None:
        """Prompt includes validation errors."""
        result = create_validation_result(
            success=False,
            stages=[
                {"stage": "lint", "success": False, "error": "E501: line too long"},
                {"stage": "test", "success": True, "error": None},
            ],
        )
        prompt = _build_fix_prompt(result, ["lint", "test"], attempt_number=1)

        assert "lint" in prompt
        assert "E501: line too long" in prompt
        # Passing stages shouldn't have errors in prompt
        assert "test:" not in prompt or "success" not in prompt.lower()

    def test_build_fix_prompt_handles_empty_stages(self) -> None:
        """Handles validation result with no stage errors."""
        result = {"success": False, "stages": []}
        prompt = _build_fix_prompt(result, ["lint"], attempt_number=1)

        assert "No specific errors provided" in prompt


class TestSummarizeErrors:
    """Tests for _summarize_errors helper function."""

    def test_summarize_errors_lists_failed_stages(self) -> None:
        """Summarizes failed stages."""
        result = create_validation_result(
            success=False,
            stages=[
                {"stage": "lint", "success": False},
                {"stage": "test", "success": True},
                {"stage": "typecheck", "success": False},
            ],
        )
        summary = _summarize_errors(result)

        assert "2 stage(s)" in summary
        assert "lint" in summary
        assert "typecheck" in summary
        assert "test" not in summary

    def test_summarize_errors_handles_no_failures(self) -> None:
        """Handles case with no failed stages."""
        result = {"success": True, "stages": []}
        summary = _summarize_errors(result)

        assert "validation failures" in summary

    def test_summarize_errors_handles_missing_stage_name(self) -> None:
        """Handles stages without name field."""
        result = {
            "success": False,
            "stages": [{"success": False}],  # No "stage" field
        }
        summary = _summarize_errors(result)

        assert "1 stage(s)" in summary
        assert "unknown" in summary


class TestRunFixRetryLoopIntegration:
    """Integration-style tests combining multiple behaviors."""

    @pytest.mark.asyncio
    async def test_full_retry_workflow_multiple_attempts_then_success(self) -> None:
        """Test complete workflow: fail twice, then succeed on third attempt."""
        initial_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            patch("maverick.library.actions.validation.asyncio.sleep") as mock_sleep,
        ):
            # Attempt 1: fix succeeds, validation fails
            # Attempt 2: fix fails, validation fails
            # Attempt 3: fix succeeds, validation passes
            mock_fixer.side_effect = [
                create_fix_result(success=True, changes_made="Partial fix"),
                create_fix_result(success=False, error="Could not complete fix"),
                create_fix_result(success=True, changes_made="Complete fix"),
            ]
            mock_validation.side_effect = [
                create_validation_result(success=False),
                create_validation_result(success=False),
                create_validation_result(success=True),
            ]
            mock_sleep.return_value = None

            result = await run_fix_retry_loop(
                stages=["lint", "test"],
                max_attempts=5,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            # Verify workflow completed successfully
            assert result["passed"] is True
            assert result["attempts"] == 3
            assert len(result["fixes_applied"]) == 3
            assert "Partial fix" in result["fixes_applied"][0]
            assert "Could not complete fix" in result["fixes_applied"][1]
            assert "Complete fix" in result["fixes_applied"][2]

            # Verify backoff was applied for attempts 2 and 3
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list[0].args[0] == 1.0  # Before attempt 2
            assert mock_sleep.call_args_list[1].args[0] == 2.0  # Before attempt 3

    @pytest.mark.asyncio
    async def test_fixer_fails_but_validation_passes_anyway(self) -> None:
        """Test case where fix appears to fail but validation passes anyway.

        This can happen if the fix was partially applied or the issue
        resolved itself (e.g., external dependency fix).
        """
        initial_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            # Fixer reports failure but validation passes
            mock_fixer.return_value = create_fix_result(
                success=False, error="Timeout waiting for response"
            )
            mock_validation.return_value = create_validation_result(success=True)

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            # Should still report success because validation passed
            assert result["passed"] is True
            assert result["attempts"] == 1
            # Fix failure should be recorded
            assert "failed" in result["fixes_applied"][0].lower()
            assert "Timeout" in result["fixes_applied"][0]
