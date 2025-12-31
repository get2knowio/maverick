"""AgentResult assertion helpers for testing.

This module provides assertion helpers for testing AgentResult objects
with clear, descriptive error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.agents.result import AgentResult


class AgentResultAssertion:
    """Helper class for asserting on AgentResult contents.

    Provides methods for common assertions on AgentResult objects with
    clear error messages that include relevant context.

    Example:
        >>> result = agent.execute(context)
        >>> AgentResultAssertion.assert_success(result)
        >>> AgentResultAssertion.assert_output_contains(result, "completed")
        >>> AgentResultAssertion.assert_usage(result, min_tokens=50)
    """

    @staticmethod
    def assert_success(result: AgentResult) -> None:
        """Assert that the result indicates success.

        Args:
            result: The AgentResult to check

        Raises:
            AssertionError: If result.success is False
        """
        if not result.success:
            error_msgs = [str(e) for e in result.errors]
            raise AssertionError(
                f"Expected successful result, but got failure.\n"
                f"Errors: {error_msgs}\n"
                f"Output: {result.output[:500]}..."
                if len(result.output) > 500
                else f"Output: {result.output}"
            )

    @staticmethod
    def assert_failure(
        result: AgentResult,
        error_type: type | None = None,
    ) -> None:
        """Assert that the result indicates failure.

        Args:
            result: The AgentResult to check
            error_type: Optional specific error type to check for

        Raises:
            AssertionError: If result.success is True or error_type doesn't match
        """
        if result.success:
            raise AssertionError(
                f"Expected failed result, but got success.\nOutput: {result.output}"
            )

        if error_type is not None:
            matching_errors = [e for e in result.errors if isinstance(e, error_type)]
            if not matching_errors:
                actual_types = [type(e).__name__ for e in result.errors]
                raise AssertionError(
                    f"Expected error of type {error_type.__name__}, "
                    f"but got: {actual_types}"
                )

    @staticmethod
    def assert_output_contains(result: AgentResult, expected: str) -> None:
        """Assert that the result output contains the expected string.

        Args:
            result: The AgentResult to check
            expected: String expected to be in the output

        Raises:
            AssertionError: If expected string is not in output
        """
        if expected not in result.output:
            raise AssertionError(
                f"Expected output to contain '{expected}'.\n"
                f"Actual output: {result.output[:1000]}..."
                if len(result.output) > 1000
                else f"Actual output: {result.output}"
            )

    @staticmethod
    def assert_output_not_contains(result: AgentResult, unexpected: str) -> None:
        """Assert that the result output does not contain the string.

        Args:
            result: The AgentResult to check
            unexpected: String that should not be in the output

        Raises:
            AssertionError: If unexpected string is in output
        """
        if unexpected in result.output:
            raise AssertionError(
                f"Expected output to NOT contain '{unexpected}'.\n"
                f"Actual output: {result.output[:1000]}..."
                if len(result.output) > 1000
                else f"Actual output: {result.output}"
            )

    @staticmethod
    def assert_usage(
        result: AgentResult,
        min_tokens: int | None = None,
        max_tokens: int | None = None,
        max_cost: float | None = None,
    ) -> None:
        """Assert that usage statistics are within expected bounds.

        Args:
            result: The AgentResult to check
            min_tokens: Minimum total tokens expected (optional)
            max_tokens: Maximum total tokens expected (optional)
            max_cost: Maximum cost in USD expected (optional)

        Raises:
            AssertionError: If usage is outside expected bounds
        """
        total = result.usage.total_tokens

        if min_tokens is not None and total < min_tokens:
            raise AssertionError(
                f"Expected at least {min_tokens} tokens, but got {total}"
            )

        if max_tokens is not None and total > max_tokens:
            raise AssertionError(
                f"Expected at most {max_tokens} tokens, but got {total}"
            )

        if max_cost is not None:
            cost = result.usage.total_cost_usd
            if cost is not None and cost > max_cost:
                raise AssertionError(
                    f"Expected cost at most ${max_cost:.4f}, but got ${cost:.4f}"
                )

    @staticmethod
    def assert_metadata_contains(
        result: AgentResult, key: str, value: object = ...
    ) -> None:
        """Assert that metadata contains a specific key (and optionally value).

        Args:
            result: The AgentResult to check
            key: Key expected in metadata
            value: Optional value to check (use ... to skip value check)

        Raises:
            AssertionError: If key not in metadata or value doesn't match
        """
        if key not in result.metadata:
            raise AssertionError(
                f"Expected metadata to contain key '{key}'.\n"
                f"Actual metadata keys: {list(result.metadata.keys())}"
            )

        if value is not ...:
            actual = result.metadata[key]
            if actual != value:
                raise AssertionError(
                    f"Expected metadata['{key}'] to be {value!r}, but got {actual!r}"
                )
