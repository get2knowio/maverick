"""Tests for FixerResult Pydantic model.

Covers construction, serialization round-trip, validation rules,
and the error_details-required-when-failure invariant.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.models.fixer import FixerResult


class TestFixerResultConstruction:
    """Tests for FixerResult construction and field defaults."""

    def test_success_case_minimal(self) -> None:
        """FixerResult can be created with only required fields for success."""
        result = FixerResult(success=True, summary="Applied formatting fix")
        assert result.success is True
        assert result.summary == "Applied formatting fix"
        assert result.files_mentioned == []
        assert result.error_details is None

    def test_success_case_with_files(self) -> None:
        """FixerResult includes files_mentioned when provided."""
        result = FixerResult(
            success=True,
            summary="Fixed import order",
            files_mentioned=["src/foo.py", "src/bar.py"],
        )
        assert result.files_mentioned == ["src/foo.py", "src/bar.py"]

    def test_failure_case_with_error_details(self) -> None:
        """FixerResult failure requires error_details."""
        result = FixerResult(
            success=False,
            summary="Could not apply fix",
            error_details="File not found: src/missing.py",
        )
        assert result.success is False
        assert result.error_details == "File not found: src/missing.py"

    def test_failure_without_error_details_raises(self) -> None:
        """FixerResult with success=False and no error_details raises."""
        with pytest.raises(ValidationError, match="error_details"):
            FixerResult(success=False, summary="Failed")

    def test_failure_with_empty_error_details_raises(self) -> None:
        """FixerResult with success=False and empty error_details raises."""
        with pytest.raises(ValidationError, match="error_details"):
            FixerResult(success=False, summary="Failed", error_details="")

    def test_success_with_error_details_allowed(self) -> None:
        """FixerResult success=True with error_details is allowed (warnings)."""
        result = FixerResult(
            success=True,
            summary="Fixed with warnings",
            error_details="Non-critical warning",
        )
        assert result.success is True
        assert result.error_details == "Non-critical warning"


class TestFixerResultImmutability:
    """Tests for frozen model behavior."""

    def test_frozen_success(self) -> None:
        """FixerResult fields cannot be mutated."""
        result = FixerResult(success=True, summary="Done")
        with pytest.raises(ValidationError):
            result.success = False  # type: ignore[misc]

    def test_frozen_summary(self) -> None:
        """FixerResult summary cannot be mutated."""
        result = FixerResult(success=True, summary="Done")
        with pytest.raises(ValidationError):
            result.summary = "Changed"  # type: ignore[misc]


class TestFixerResultSerialization:
    """Tests for model_dump / model_validate round-trip."""

    def test_round_trip_success(self) -> None:
        """model_dump -> model_validate preserves all fields."""
        original = FixerResult(
            success=True,
            summary="Applied fix",
            files_mentioned=["src/a.py", "src/b.py"],
        )
        data = original.model_dump()
        restored = FixerResult.model_validate(data)
        assert restored == original

    def test_round_trip_failure(self) -> None:
        """model_dump -> model_validate preserves failure state."""
        original = FixerResult(
            success=False,
            summary="Fix failed",
            error_details="Syntax error in generated code",
            files_mentioned=["src/broken.py"],
        )
        data = original.model_dump()
        restored = FixerResult.model_validate(data)
        assert restored == original

    def test_to_dict_alias(self) -> None:
        """to_dict() is an alias for model_dump(exclude_none=True)."""
        result = FixerResult(success=True, summary="Done")
        assert result.to_dict() == result.model_dump(exclude_none=True)

    def test_from_dict_alias(self) -> None:
        """from_dict() is an alias for model_validate()."""
        data = {"success": True, "summary": "Done"}
        result = FixerResult.from_dict(data)
        assert result.success is True
        assert result.summary == "Done"

    def test_json_round_trip(self) -> None:
        """model_dump_json -> model_validate_json preserves all fields."""
        original = FixerResult(
            success=True,
            summary="Applied fix",
            files_mentioned=["src/a.py"],
        )
        json_str = original.model_dump_json()
        restored = FixerResult.model_validate_json(json_str)
        assert restored == original


class TestFixerResultSchemaGeneration:
    """Tests for JSON schema generation (used by SDK output_format)."""

    def test_json_schema_has_required_fields(self) -> None:
        """model_json_schema() includes all required fields."""
        schema = FixerResult.model_json_schema()
        assert "success" in schema["properties"]
        assert "summary" in schema["properties"]
        assert "files_mentioned" in schema["properties"]
        assert "error_details" in schema["properties"]
        assert "success" in schema["required"]
        assert "summary" in schema["required"]
