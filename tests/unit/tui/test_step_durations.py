"""Unit tests for step duration tracking module.

This test module covers:
- StepDuration dataclass creation and methods
- StepDurationStore persistence and retrieval
- ETACalculator estimation methods

Feature: 030-tui-execution-visibility
Date: 2026-01-12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.tui.step_durations import (
    ETACalculator,
    StepDuration,
    StepDurationStore,
)


class TestStepDuration:
    """Tests for StepDuration dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating StepDuration with all fields."""
        step = StepDuration(
            workflow_name="feature",
            step_name="validate",
            durations=(1.5, 2.0, 1.8),
            average=1.77,
        )

        assert step.workflow_name == "feature"
        assert step.step_name == "validate"
        assert step.durations == (1.5, 2.0, 1.8)
        assert step.average == 1.77

    def test_create_calculates_average(self) -> None:
        """Test create() calculates average correctly."""
        step = StepDuration.create("feature", "validate", [1.0, 2.0, 3.0])

        assert step.workflow_name == "feature"
        assert step.step_name == "validate"
        assert step.durations == (1.0, 2.0, 3.0)
        assert step.average == 2.0

    def test_create_empty_durations(self) -> None:
        """Test create() with empty durations."""
        step = StepDuration.create("feature", "validate", [])

        assert step.durations == ()
        assert step.average == 0.0

    def test_add_duration_single(self) -> None:
        """Test add_duration creates new instance with added duration."""
        step = StepDuration.create("feature", "validate", [1.0, 2.0])
        new_step = step.add_duration(3.0)

        # Original unchanged
        assert len(step.durations) == 2

        # New has added duration
        assert len(new_step.durations) == 3
        assert new_step.durations[-1] == 3.0
        assert new_step.average == 2.0

    def test_add_duration_respects_max_history(self) -> None:
        """Test add_duration respects max_history limit."""
        step = StepDuration.create("feature", "validate", list(range(1, 11)))
        assert len(step.durations) == 10

        new_step = step.add_duration(11.0, max_history=10)

        # Should have 10 items, oldest dropped
        assert len(new_step.durations) == 10
        assert new_step.durations[0] == 2  # Oldest (1) dropped
        assert new_step.durations[-1] == 11.0

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        step = StepDuration(
            workflow_name="feature",
            step_name="validate",
            durations=(1.0, 2.0),
            average=1.5,
        )

        data = step.to_dict()

        assert data["workflow_name"] == "feature"
        assert data["step_name"] == "validate"
        assert data["durations"] == [1.0, 2.0]
        assert data["average"] == 1.5

    def test_from_dict(self) -> None:
        """Test from_dict deserialization."""
        data = {
            "workflow_name": "feature",
            "step_name": "validate",
            "durations": [1.0, 2.0, 3.0],
            "average": 2.0,
        }

        step = StepDuration.from_dict(data)

        assert step.workflow_name == "feature"
        assert step.step_name == "validate"
        assert step.durations == (1.0, 2.0, 3.0)
        assert step.average == 2.0

    def test_step_is_frozen(self) -> None:
        """Test that StepDuration is immutable."""
        step = StepDuration.create("feature", "validate", [1.0])

        with pytest.raises(Exception):  # FrozenInstanceError
            step.average = 5.0  # type: ignore[misc]


class TestStepDurationStore:
    """Tests for StepDurationStore."""

    @pytest.fixture
    def temp_store(self, tmp_path: Path) -> StepDurationStore:
        """Create a store with temporary path."""
        return StepDurationStore(path=tmp_path / "durations.json")

    def test_make_key(self, temp_store: StepDurationStore) -> None:
        """Test _make_key creates correct key format."""
        key = temp_store._make_key("feature", "validate")
        assert key == "feature:validate"

    def test_load_empty_store(self, temp_store: StepDurationStore) -> None:
        """Test load returns empty dict when no file."""
        data = temp_store.load()
        assert data == {}

    def test_record_and_get_average(self, temp_store: StepDurationStore) -> None:
        """Test recording duration and getting average."""
        temp_store.record_duration("feature", "validate", 1.5)
        temp_store.record_duration("feature", "validate", 2.5)

        avg = temp_store.get_average("feature", "validate")
        assert avg == 2.0

    def test_get_average_no_history(self, temp_store: StepDurationStore) -> None:
        """Test get_average returns None for unknown step."""
        avg = temp_store.get_average("unknown", "step")
        assert avg is None

    def test_persistence(self, temp_store: StepDurationStore) -> None:
        """Test data persists to disk."""
        temp_store.record_duration("feature", "validate", 1.5)

        # File should exist
        assert temp_store.path.exists()

        # Create new store instance and verify data loads
        new_store = StepDurationStore(path=temp_store.path)
        avg = new_store.get_average("feature", "validate")
        assert avg == 1.5

    def test_get_workflow_averages(self, temp_store: StepDurationStore) -> None:
        """Test get_workflow_averages returns all steps."""
        temp_store.record_duration("feature", "validate", 1.0)
        temp_store.record_duration("feature", "implement", 2.0)
        temp_store.record_duration("other", "build", 3.0)

        averages = temp_store.get_workflow_averages("feature")

        assert len(averages) == 2
        assert averages["validate"] == 1.0
        assert averages["implement"] == 2.0
        # 'other' workflow not included
        assert "build" not in averages

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test load handles invalid JSON gracefully."""
        path = tmp_path / "invalid.json"
        path.write_text("not valid json")

        store = StepDurationStore(path=path)
        data = store.load()

        assert data == {}

    def test_load_invalid_structure(self, tmp_path: Path) -> None:
        """Test load handles invalid data structure."""
        path = tmp_path / "invalid.json"
        path.write_text('["not", "a", "dict"]')

        store = StepDurationStore(path=path)
        data = store.load()

        assert data == {}

    def test_cache_behavior(self, temp_store: StepDurationStore) -> None:
        """Test cache is used after first load."""
        temp_store.record_duration("feature", "validate", 1.0)

        # First load
        temp_store.load()

        # Corrupt file
        temp_store.path.write_text('{"broken": true}')

        # Should still return cached data
        avg = temp_store.get_average("feature", "validate")
        assert avg == 1.0

    def test_multiple_workflows(self, temp_store: StepDurationStore) -> None:
        """Test storing durations for multiple workflows."""
        temp_store.record_duration("feature", "step1", 1.0)
        temp_store.record_duration("refuel", "step1", 2.0)

        assert temp_store.get_average("feature", "step1") == 1.0
        assert temp_store.get_average("refuel", "step1") == 2.0


class TestETACalculator:
    """Tests for ETACalculator."""

    @pytest.fixture
    def store_with_data(self, tmp_path: Path) -> StepDurationStore:
        """Create store with pre-populated data."""
        store = StepDurationStore(path=tmp_path / "durations.json")
        store.record_duration("feature", "validate", 5.0)
        store.record_duration("feature", "implement", 30.0)
        store.record_duration("feature", "review", 15.0)
        return store

    def test_calculate_eta_with_history(
        self, store_with_data: StepDurationStore
    ) -> None:
        """Test ETA calculation with historical data."""
        calc = ETACalculator(store=store_with_data, workflow_name="feature")

        eta = calc.calculate_eta(["validate", "implement", "review"])

        # 5 + 30 + 15 = 50
        assert eta == 50.0

    def test_calculate_eta_with_current_step(
        self, store_with_data: StepDurationStore
    ) -> None:
        """Test ETA calculation with current step elapsed time."""
        calc = ETACalculator(store=store_with_data, workflow_name="feature")

        eta = calc.calculate_eta(
            ["implement", "review"],
            current_step="implement",
            current_elapsed=10.0,
        )

        # (30 - 10) + 15 = 35
        assert eta == 35.0

    def test_calculate_eta_elapsed_exceeds_average(
        self, store_with_data: StepDurationStore
    ) -> None:
        """Test ETA when elapsed exceeds average (clamped to 0)."""
        calc = ETACalculator(store=store_with_data, workflow_name="feature")

        eta = calc.calculate_eta(
            ["validate", "review"],
            current_step="validate",
            current_elapsed=10.0,  # 10 > 5s average
        )

        # max(0, 5 - 10) + 15 = 0 + 15 = 15
        assert eta == 15.0

    def test_calculate_eta_default_duration(self, tmp_path: Path) -> None:
        """Test ETA uses default duration when no history."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(
            store=store, workflow_name="feature", default_step_duration=20.0
        )

        eta = calc.calculate_eta(["step1", "step2"])

        # 20 + 20 = 40
        assert eta == 40.0

    def test_format_eta_seconds(self, tmp_path: Path) -> None:
        """Test format_eta for seconds."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(store=store, workflow_name="feature")

        assert calc.format_eta(30) == "~30s remaining"
        assert calc.format_eta(1) == "~1s remaining"

    def test_format_eta_almost_done(self, tmp_path: Path) -> None:
        """Test format_eta when almost done."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(store=store, workflow_name="feature")

        assert calc.format_eta(0) == "almost done"
        assert calc.format_eta(-5) == "almost done"

    def test_format_eta_minutes(self, tmp_path: Path) -> None:
        """Test format_eta for minutes."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(store=store, workflow_name="feature")

        assert calc.format_eta(60) == "~1m remaining"
        assert calc.format_eta(150) == "~2m remaining"
        assert calc.format_eta(3599) == "~59m remaining"

    def test_format_eta_hours(self, tmp_path: Path) -> None:
        """Test format_eta for hours."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(store=store, workflow_name="feature")

        assert calc.format_eta(3600) == "~1h 0m remaining"
        assert calc.format_eta(5400) == "~1h 30m remaining"
        assert calc.format_eta(7200) == "~2h 0m remaining"

    def test_get_step_estimate_with_history(
        self, store_with_data: StepDurationStore
    ) -> None:
        """Test get_step_estimate returns historical average."""
        calc = ETACalculator(store=store_with_data, workflow_name="feature")

        estimate = calc.get_step_estimate("validate")

        assert estimate == 5.0

    def test_get_step_estimate_default(self, tmp_path: Path) -> None:
        """Test get_step_estimate returns default when no history."""
        store = StepDurationStore(path=tmp_path / "empty.json")
        calc = ETACalculator(
            store=store, workflow_name="feature", default_step_duration=45.0
        )

        estimate = calc.get_step_estimate("unknown_step")

        assert estimate == 45.0
