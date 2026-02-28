"""Unit tests for WorkUnitSpec and DecompositionOutput Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.workflows.refuel_maverick.models import (
    DecompositionOutput,
    FileScopeSpec,
    WorkUnitSpec,
)


def _make_valid_spec(**overrides: object) -> dict:
    """Return a valid WorkUnitSpec dict with optional overrides."""
    base = {
        "id": "valid-id",
        "sequence": 1,
        "task": "A valid task",
        "verification": ["make test"],
        "file_scope": FileScopeSpec(),
        "instructions": "Do something",
    }
    base.update(overrides)
    return base


class TestWorkUnitSpecValidation:
    """Tests for WorkUnitSpec Pydantic validators."""

    def test_valid_spec_accepted(self) -> None:
        spec = WorkUnitSpec(**_make_valid_spec())
        assert spec.id == "valid-id"

    def test_non_kebab_case_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            WorkUnitSpec(**_make_valid_spec(id="InvalidId"))

    def test_uppercase_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            WorkUnitSpec(**_make_valid_spec(id="UPPER-CASE"))

    def test_sequence_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkUnitSpec(**_make_valid_spec(sequence=0))

    def test_negative_sequence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkUnitSpec(**_make_valid_spec(sequence=-1))

    def test_empty_task_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            WorkUnitSpec(**_make_valid_spec(task=""))

    def test_whitespace_task_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            WorkUnitSpec(**_make_valid_spec(task="   "))

    def test_empty_verification_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            WorkUnitSpec(**_make_valid_spec(verification=[]))


class TestDecompositionOutputValidation:
    """Tests for DecompositionOutput Pydantic validators."""

    def test_empty_work_units_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            DecompositionOutput(work_units=[], rationale="empty")

    def test_duplicate_work_unit_ids_rejected(self) -> None:
        spec_dict = _make_valid_spec()
        spec_a = WorkUnitSpec(**spec_dict)
        spec_b = WorkUnitSpec(**{**spec_dict, "sequence": 2})
        with pytest.raises(ValidationError, match="Duplicate"):
            DecompositionOutput(
                work_units=[spec_a, spec_b], rationale="dupes"
            )

    def test_valid_decomposition_accepted(self) -> None:
        spec = WorkUnitSpec(**_make_valid_spec())
        decomp = DecompositionOutput(
            work_units=[spec], rationale="valid"
        )
        assert len(decomp.work_units) == 1
