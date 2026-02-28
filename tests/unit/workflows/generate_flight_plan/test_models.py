"""Unit tests for GenerateFlightPlanWorkflow models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.workflows.generate_flight_plan.models import (
    FlightPlanOutput,
    GenerateFlightPlanResult,
)


class TestFlightPlanOutput:
    """Tests for the FlightPlanOutput agent output schema."""

    def test_valid_output(self) -> None:
        """Valid FlightPlanOutput can be instantiated."""
        output = FlightPlanOutput(
            name="my-feature",
            version="1",
            objective="Build a CLI tool",
            success_criteria=["Tests pass", "CLI prints output"],
            in_scope=["src/main.py"],
            out_of_scope=["documentation"],
            boundaries=["Python 3.10+ only"],
            context="Background info",
            constraints=["Must use Click"],
            notes="Additional notes",
        )
        assert output.name == "my-feature"
        assert len(output.success_criteria) == 2

    def test_empty_name_rejected(self) -> None:
        """Empty name is rejected."""
        with pytest.raises(ValidationError, match="name must not be empty"):
            FlightPlanOutput(
                name="   ",
                objective="Build something",
                success_criteria=["Tests pass"],
                in_scope=["src/"],
                out_of_scope=["docs/"],
                boundaries=["Python only"],
            )

    def test_empty_objective_rejected(self) -> None:
        """Empty objective is rejected."""
        with pytest.raises(ValidationError, match="objective must not be empty"):
            FlightPlanOutput(
                name="test",
                objective="",
                success_criteria=["Tests pass"],
                in_scope=["src/"],
                out_of_scope=["docs/"],
                boundaries=["Python only"],
            )

    def test_empty_success_criteria_rejected(self) -> None:
        """Empty success_criteria list is rejected."""
        with pytest.raises(ValidationError, match="success_criteria must not be empty"):
            FlightPlanOutput(
                name="test",
                objective="Build it",
                success_criteria=[],
                in_scope=["src/"],
                out_of_scope=["docs/"],
                boundaries=["Python only"],
            )

    def test_empty_in_scope_rejected(self) -> None:
        """Empty in_scope list is rejected."""
        with pytest.raises(ValidationError, match="in_scope must not be empty"):
            FlightPlanOutput(
                name="test",
                objective="Build it",
                success_criteria=["Tests pass"],
                in_scope=[],
                out_of_scope=["docs/"],
                boundaries=["Python only"],
            )

    def test_defaults_applied(self) -> None:
        """Optional fields get their defaults."""
        output = FlightPlanOutput(
            name="test",
            objective="Build it",
            success_criteria=["Tests pass"],
            in_scope=["src/"],
            out_of_scope=["docs/"],
            boundaries=["Python only"],
        )
        assert output.version == "1"
        assert output.context == ""
        assert output.constraints == []
        assert output.notes == ""

    def test_frozen_model(self) -> None:
        """FlightPlanOutput is immutable."""
        output = FlightPlanOutput(
            name="test",
            objective="Build it",
            success_criteria=["Tests pass"],
            in_scope=["src/"],
            out_of_scope=["docs/"],
            boundaries=["Python only"],
        )
        with pytest.raises(ValidationError):
            output.name = "modified"  # type: ignore[misc]


class TestGenerateFlightPlanResult:
    """Tests for the GenerateFlightPlanResult dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() returns all fields."""
        result = GenerateFlightPlanResult(
            flight_plan_path=".maverick/flight-plans/my-plan.md",
            name="my-plan",
            success_criteria_count=5,
            validation_passed=True,
        )
        d = result.to_dict()
        assert d["flight_plan_path"] == ".maverick/flight-plans/my-plan.md"
        assert d["name"] == "my-plan"
        assert d["success_criteria_count"] == 5
        assert d["validation_passed"] is True

    def test_frozen(self) -> None:
        """Result is immutable."""
        result = GenerateFlightPlanResult(
            flight_plan_path="test.md",
            name="test",
            success_criteria_count=1,
            validation_passed=True,
        )
        with pytest.raises(AttributeError):
            result.name = "modified"  # type: ignore[misc]
