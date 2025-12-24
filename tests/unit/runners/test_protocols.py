"""Unit tests for runner protocols.

Tests the ValidatableRunner protocol for runtime checkability
and proper structural subtyping behavior.
"""

from __future__ import annotations

import pytest

from maverick.runners.preflight import ValidationResult
from maverick.runners.protocols import ValidatableRunner

# --- Mock implementations for testing ---


class ValidRunner:
    """Mock runner that properly implements ValidatableRunner."""

    async def validate(self) -> ValidationResult:
        """Return a successful validation result."""
        return ValidationResult(
            success=True,
            component="ValidRunner",
            errors=(),
            warnings=(),
            duration_ms=10,
        )


class ValidRunnerWithWarnings:
    """Mock runner that returns validation with warnings."""

    async def validate(self) -> ValidationResult:
        """Return a result with warnings but still successful."""
        return ValidationResult(
            success=True,
            component="ValidRunnerWithWarnings",
            errors=(),
            warnings=("Consider upgrading tool version",),
            duration_ms=25,
        )


class FailingRunner:
    """Mock runner that returns a failed validation."""

    async def validate(self) -> ValidationResult:
        """Return a failed validation result."""
        return ValidationResult(
            success=False,
            component="FailingRunner",
            errors=("Required tool not found",),
            warnings=(),
            duration_ms=5,
        )


class InvalidRunner:
    """Mock class that does NOT implement validate()."""

    async def other_method(self) -> str:
        """Some other method, not validate."""
        return "not a validatable runner"


class SyncValidateRunner:
    """Mock class with sync validate() - wrong signature."""

    def validate(self) -> ValidationResult:
        """Sync validate - doesn't match async protocol."""
        return ValidationResult(
            success=True,
            component="SyncValidateRunner",
        )


class WrongReturnTypeRunner:
    """Mock class with validate() returning wrong type."""

    async def validate(self) -> dict:
        """Returns dict instead of ValidationResult."""
        return {"success": True}


# --- Protocol compliance tests ---


class TestValidatableRunnerProtocol:
    """Tests for ValidatableRunner protocol compliance."""

    def test_valid_runner_is_instance(self) -> None:
        """Test that a class with validate() is recognized as ValidatableRunner."""
        runner = ValidRunner()
        assert isinstance(runner, ValidatableRunner)

    def test_invalid_runner_is_not_instance(self) -> None:
        """Test that a class without validate() is NOT recognized."""
        runner = InvalidRunner()
        assert not isinstance(runner, ValidatableRunner)

    def test_runtime_checkable_with_isinstance(self) -> None:
        """Test isinstance() works due to @runtime_checkable decorator."""
        valid = ValidRunner()
        invalid = InvalidRunner()

        # isinstance checks work at runtime
        assert isinstance(valid, ValidatableRunner) is True
        assert isinstance(invalid, ValidatableRunner) is False

    def test_failing_runner_still_implements_protocol(self) -> None:
        """Test that a runner returning failures still satisfies protocol."""
        runner = FailingRunner()
        assert isinstance(runner, ValidatableRunner)

    def test_runner_with_warnings_implements_protocol(self) -> None:
        """Test runner with warnings satisfies protocol."""
        runner = ValidRunnerWithWarnings()
        assert isinstance(runner, ValidatableRunner)

    def test_sync_validate_still_matches_protocol(self) -> None:
        """Test sync validate matches protocol (runtime_checkable is structural).

        Note: runtime_checkable only checks method existence, not signature.
        Type checkers would catch the async/sync mismatch at static analysis time.
        """
        runner = SyncValidateRunner()
        # runtime_checkable doesn't verify async - only method existence
        assert isinstance(runner, ValidatableRunner)

    def test_wrong_return_type_still_matches_structurally(self) -> None:
        """Test wrong return type matches protocol structurally.

        Note: runtime_checkable only checks method existence.
        Type checkers catch return type mismatches at static analysis time.
        """
        runner = WrongReturnTypeRunner()
        # runtime_checkable doesn't verify return types
        assert isinstance(runner, ValidatableRunner)


# --- Async validation tests ---


class TestValidatableRunnerValidation:
    """Tests for ValidatableRunner.validate() behavior."""

    @pytest.mark.asyncio
    async def test_validate_returns_validation_result(self) -> None:
        """Test that validate() returns a ValidationResult."""
        runner = ValidRunner()
        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is True
        assert result.component == "ValidRunner"

    @pytest.mark.asyncio
    async def test_validate_with_errors(self) -> None:
        """Test validate() with failed result containing errors."""
        runner = FailingRunner()
        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is False
        assert "Required tool not found" in result.errors
        assert result.component == "FailingRunner"

    @pytest.mark.asyncio
    async def test_validate_with_warnings(self) -> None:
        """Test validate() with successful result containing warnings."""
        runner = ValidRunnerWithWarnings()
        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is True
        assert len(result.warnings) == 1
        assert "Consider upgrading" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_validate_includes_duration(self) -> None:
        """Test that ValidationResult includes duration_ms."""
        runner = ValidRunner()
        result = await runner.validate()

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_multiple_runners_can_be_validated(self) -> None:
        """Test validating multiple protocol-conforming runners."""
        runners: list[ValidatableRunner] = [
            ValidRunner(),
            ValidRunnerWithWarnings(),
            FailingRunner(),
        ]

        results = [await r.validate() for r in runners]

        assert len(results) == 3
        assert all(isinstance(r, ValidationResult) for r in results)
        # First two succeed, third fails
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is False


# --- Edge cases ---


class TestValidatableRunnerEdgeCases:
    """Edge case tests for ValidatableRunner."""

    def test_class_is_also_instance(self) -> None:
        """Test that class itself is recognized (has validate method).

        Note: runtime_checkable protocols check for attribute existence,
        and the class has a validate method (unbound), so it matches.
        """
        assert isinstance(ValidRunner, ValidatableRunner)

    def test_none_is_not_instance(self) -> None:
        """Test that None is not recognized as ValidatableRunner."""
        assert not isinstance(None, ValidatableRunner)

    def test_dict_is_not_instance(self) -> None:
        """Test that a dict is not recognized as ValidatableRunner."""
        assert not isinstance({"validate": lambda: None}, ValidatableRunner)

    @pytest.mark.asyncio
    async def test_validation_result_is_frozen(self) -> None:
        """Test that ValidationResult is immutable (frozen dataclass)."""
        runner = ValidRunner()
        result = await runner.validate()

        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]
