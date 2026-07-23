"""Tests for the Spec Kit error hierarchy."""

from __future__ import annotations

from maverick.exceptions.base import MaverickError
from maverick.speckit.errors import (
    AmbiguousFeatureError,
    NothingToIngestError,
    SpeckitError,
    SpeckitParseError,
    SpeckitValidationError,
    UnsupportedTemplateError,
)


def test_speckit_error_is_a_maverick_error() -> None:
    assert issubclass(SpeckitError, MaverickError)


def test_speckit_parse_error_carries_file_line_expected_suggestion() -> None:
    err = SpeckitParseError(
        "malformed task line",
        file="tasks.md",
        line=12,
        expected="- [ ] T### description",
        suggestion="add a task ID",
    )
    assert isinstance(err, SpeckitError)
    assert err.file == "tasks.md"
    assert err.line == 12
    assert err.expected == "- [ ] T### description"
    assert err.suggestion == "add a task ID"
    assert "malformed task line" in str(err)


def test_speckit_validation_error_carries_duplicate_id_context() -> None:
    err = SpeckitValidationError(
        "duplicate task ID T005",
        file="tasks.md",
        task_id="T005",
        lines=(10, 20),
    )
    assert err.task_id == "T005"
    assert err.lines == (10, 20)
    assert "T005" in str(err)


def test_speckit_validation_error_carries_unknown_ref() -> None:
    err = SpeckitValidationError(
        "unknown dependency T999",
        task_id="T001",
        unknown_ref="T999",
    )
    assert err.unknown_ref == "T999"


def test_ambiguous_feature_error_carries_candidates() -> None:
    err = AmbiguousFeatureError(
        "multiple matches",
        query="048",
        candidates=("specs/048-a", "specs/048-b"),
    )
    assert err.query == "048"
    assert err.candidates == ("specs/048-a", "specs/048-b")


def test_unsupported_template_error_carries_versions() -> None:
    err = UnsupportedTemplateError(
        "unsupported template version 0.99.0, supported: >=0.14,<0.15",
        found_version="0.99.0",
        supported_range=">=0.14,<0.15",
    )
    assert err.found_version == "0.99.0"
    assert err.supported_range == ">=0.14,<0.15"
    assert "0.99.0" in str(err)


def test_nothing_to_ingest_error_carries_counts() -> None:
    err = NothingToIngestError(
        "nothing to ingest",
        completed_count=5,
        total_count=5,
    )
    assert err.completed_count == 5
    assert err.total_count == 5
