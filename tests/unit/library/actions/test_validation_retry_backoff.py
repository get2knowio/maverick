"""Unit tests for exponential backoff behavior in fix retry loop.

Tests the exponential backoff mechanism between retry attempts.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from maverick.library.actions.validation import run_fix_retry_loop

from .conftest import create_fix_result, create_validation_result


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
