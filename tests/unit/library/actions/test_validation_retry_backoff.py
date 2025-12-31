"""Unit tests for exponential backoff behavior in fix retry loop.

Tests verify that tenacity is configured with exponential backoff.
The actual wait timing is delegated to tenacity; we verify configuration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.validation import run_fix_retry_loop

from .conftest import create_fix_result, create_validation_result


class TestRunFixRetryLoopExponentialBackoff:
    """Tests for exponential backoff behavior with tenacity."""

    @pytest.mark.asyncio
    async def test_run_fix_retry_loop_applies_exponential_backoff(self) -> None:
        """Verify backoff is applied between attempts via tenacity."""
        validation_result = create_validation_result(success=False)

        with (
            patch(
                "maverick.library.actions.validation._invoke_fixer_agent"
            ) as mock_fixer,
            patch(
                "maverick.library.actions.validation._run_validation"
            ) as mock_validation,
            # Patch asyncio.sleep which tenacity uses for async waiting
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=False)

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=4,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Tenacity applies backoff between retries (not before first attempt)
            # Backoff is called for attempts 2, 3, 4 (3 times total)
            assert mock_sleep.call_count == 3
            # Verify exponential backoff pattern (values within tenacity's range)
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            # Each value should be >= the minimum (1s) and growing exponentially
            assert sleep_calls[0] >= 1.0
            assert sleep_calls[1] >= sleep_calls[0]
            assert sleep_calls[2] >= sleep_calls[1]

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
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_fixer.return_value = create_fix_result(success=True)
            mock_validation.return_value = create_validation_result(success=True)

            await run_fix_retry_loop(
                stages=["lint"],
                max_attempts=3,
                fixer_agent="fixer",
                validation_result=validation_result,
            )

            # Only one attempt needed, no backoff
            mock_sleep.assert_not_called()
