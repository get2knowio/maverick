"""Integration tests for fix retry loop.

Tests complete workflows combining multiple behaviors including:
- Multiple retry attempts
- Mixed success/failure scenarios
- Edge cases

Note: Since the code uses tenacity for retries, we mock the internal
functions rather than asyncio.sleep directly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from maverick.library.actions.validation import run_fix_retry_loop

from .conftest import create_fix_result, create_validation_result


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
            # Patch tenacity's wait to avoid actual delays
            patch("tenacity.nap.sleep"),
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

    @pytest.mark.asyncio
    async def test_max_attempts_exhausted(self) -> None:
        """Test that workflow stops after max_attempts and reports failure."""
        initial_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            # Patch tenacity's wait to avoid actual delays
            patch("tenacity.nap.sleep"),
        ):
            # All attempts fail
            mock_fixer.return_value = create_fix_result(
                success=True, changes_made="Applied fix"
            )
            mock_validation.return_value = create_validation_result(success=False)

            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            # Verify all attempts were made
            assert result["passed"] is False
            assert result["attempts"] == 3
            assert len(result["fixes_applied"]) == 3

    @pytest.mark.asyncio
    async def test_initial_validation_passed_no_retries(self) -> None:
        """Test that no retries occur when initial validation passes."""
        initial_result = create_validation_result(success=True)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            # Should return immediately without any fix attempts
            assert result["passed"] is True
            assert result["attempts"] == 0
            assert len(result["fixes_applied"]) == 0
            mock_fixer.assert_not_called()
            mock_validation.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_attempts_zero_no_retries(self) -> None:
        """Test that max_attempts=0 disables retries."""
        initial_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
        ):
            result = await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=0,
                fixer_agent="fixer",
                validation_result=initial_result,
            )

            # Should return failure without any fix attempts
            assert result["passed"] is False
            assert result["attempts"] == 0
            assert len(result["fixes_applied"]) == 0
            mock_fixer.assert_not_called()
            mock_validation.assert_not_called()
