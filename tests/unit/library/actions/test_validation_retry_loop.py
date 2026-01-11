"""Unit tests for run_fix_retry_loop core behavior.

Tests the main retry loop logic including:
- Immediate pass when validation succeeds
- Skipping when max_attempts is 0
- Fixer agent invocation
- Validation re-runs after fixes
- Max attempts exhaustion
- Error handling and graceful failure
- Recording fix attempts
- Working directory handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.validation import run_fix_retry_loop

from .conftest import create_fix_result, create_validation_result


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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # Fixer always succeeds but validation always fails
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=False)

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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
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
            # Patch tenacity's sleep to avoid test delays
            patch("asyncio.sleep", new_callable=AsyncMock),
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
            stage_results={
                "lint": {
                    "passed": False,
                    "output": "",
                    "errors": [{"message": "E501: line too long"}],
                },
                "test": {
                    "passed": False,
                    "output": "",
                    "errors": [{"message": "AssertionError"}],
                },
            },
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
