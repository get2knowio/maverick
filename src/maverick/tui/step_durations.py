"""Step duration tracking for ETA calculations.

This module provides persistence and calculation of step durations
to enable accurate ETA estimates during workflow execution.

Feature: TUI Dramatic Improvement - Sprint 2
Date: 2026-01-12
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maverick.utils.atomic import atomic_write_json

__all__ = [
    "DURATION_PATH",
    "StepDuration",
    "StepDurationStore",
    "ETACalculator",
]

DURATION_PATH = Path.home() / ".config" / "maverick" / "step_durations.json"


@dataclass(frozen=True, slots=True)
class StepDuration:
    """Historical duration record for a workflow step.

    Attributes:
        workflow_name: Name of the workflow.
        step_name: Name of the step.
        durations: List of historical durations in seconds.
        average: Calculated average duration.
    """

    workflow_name: str
    step_name: str
    durations: tuple[float, ...]
    average: float

    @classmethod
    def create(
        cls,
        workflow_name: str,
        step_name: str,
        durations: list[float],
    ) -> StepDuration:
        """Create a StepDuration with calculated average.

        Args:
            workflow_name: Name of the workflow.
            step_name: Name of the step.
            durations: List of historical durations.

        Returns:
            New StepDuration instance.
        """
        avg = sum(durations) / len(durations) if durations else 0.0
        return cls(
            workflow_name=workflow_name,
            step_name=step_name,
            durations=tuple(durations),
            average=avg,
        )

    def add_duration(self, duration: float, max_history: int = 10) -> StepDuration:
        """Create new instance with added duration.

        Keeps only the most recent max_history durations.

        Args:
            duration: Duration to add in seconds.
            max_history: Maximum durations to keep.

        Returns:
            New StepDuration with updated durations and average.
        """
        new_durations = list(self.durations[-max_history + 1 :]) + [duration]
        return StepDuration.create(self.workflow_name, self.step_name, new_durations)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "workflow_name": self.workflow_name,
            "step_name": self.step_name,
            "durations": list(self.durations),
            "average": self.average,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepDuration:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            workflow_name=data["workflow_name"],
            step_name=data["step_name"],
            durations=tuple(data["durations"]),
            average=data["average"],
        )


@dataclass
class StepDurationStore:
    """Persistent storage for step duration history.

    Stores historical step durations per workflow to enable
    accurate ETA calculations.
    """

    path: Path = field(default_factory=lambda: DURATION_PATH)
    _cache: dict[str, StepDuration] | None = field(default=None, repr=False)

    def _make_key(self, workflow_name: str, step_name: str) -> str:
        """Create unique key for workflow+step combination."""
        return f"{workflow_name}:{step_name}"

    def load(self) -> dict[str, StepDuration]:
        """Load duration records from disk.

        Returns:
            Dictionary mapping workflow:step to StepDuration.
        """
        if self._cache is not None:
            return self._cache

        if not self.path.exists():
            self._cache = {}
            return self._cache

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self._cache = {}
                return self._cache

            self._cache = {}
            for key, item in data.items():
                try:
                    self._cache[key] = StepDuration.from_dict(item)
                except (KeyError, TypeError, ValueError):
                    continue

            return self._cache

        except (json.JSONDecodeError, OSError):
            self._cache = {}
            return self._cache

    def save(self) -> None:
        """Save duration records to disk."""
        if self._cache is None:
            return

        data = {key: dur.to_dict() for key, dur in self._cache.items()}
        atomic_write_json(self.path, data, indent=2, ensure_ascii=False, mkdir=True)

    def get_average(self, workflow_name: str, step_name: str) -> float | None:
        """Get average duration for a step.

        Args:
            workflow_name: Name of the workflow.
            step_name: Name of the step.

        Returns:
            Average duration in seconds, or None if no history.
        """
        durations = self.load()
        key = self._make_key(workflow_name, step_name)
        step_dur = durations.get(key)
        if step_dur and step_dur.durations:
            return step_dur.average
        return None

    def record_duration(
        self,
        workflow_name: str,
        step_name: str,
        duration: float,
    ) -> None:
        """Record a step duration.

        Args:
            workflow_name: Name of the workflow.
            step_name: Name of the step.
            duration: Duration in seconds.
        """
        durations = self.load()
        key = self._make_key(workflow_name, step_name)

        if key in durations:
            durations[key] = durations[key].add_duration(duration)
        else:
            durations[key] = StepDuration.create(workflow_name, step_name, [duration])

        self.save()

    def get_workflow_averages(self, workflow_name: str) -> dict[str, float]:
        """Get all step averages for a workflow.

        Args:
            workflow_name: Name of the workflow.

        Returns:
            Dictionary mapping step name to average duration.
        """
        durations = self.load()
        prefix = f"{workflow_name}:"
        result = {}
        for key, step_dur in durations.items():
            if key.startswith(prefix) and step_dur.durations:
                step_name = key[len(prefix) :]
                result[step_name] = step_dur.average
        return result


@dataclass(frozen=True, slots=True)
class ETACalculator:
    """Calculate estimated time remaining for workflow execution.

    Uses historical step durations to provide accurate ETA estimates.
    Falls back to default estimates when no history is available.
    """

    store: StepDurationStore
    workflow_name: str
    default_step_duration: float = 30.0  # Default 30s per step

    def calculate_eta(
        self,
        remaining_steps: list[str],
        current_step: str | None = None,
        current_elapsed: float = 0.0,
    ) -> float:
        """Calculate estimated time remaining.

        Args:
            remaining_steps: List of step names not yet completed.
            current_step: Currently running step (if any).
            current_elapsed: Time already elapsed on current step.

        Returns:
            Estimated remaining time in seconds.
        """
        averages = self.store.get_workflow_averages(self.workflow_name)
        total = 0.0

        for step in remaining_steps:
            avg = averages.get(step, self.default_step_duration)
            if step == current_step:
                # Subtract already elapsed time from estimate
                remaining = max(0.0, avg - current_elapsed)
                total += remaining
            else:
                total += avg

        return total

    def format_eta(self, seconds: float) -> str:
        """Format ETA for display.

        Args:
            seconds: Remaining time in seconds.

        Returns:
            Human-readable ETA string.
        """
        if seconds <= 0:
            return "almost done"
        if seconds < 60:
            return f"~{int(seconds)}s remaining"
        if seconds < 3600:
            minutes = int(seconds // 60)
            return f"~{minutes}m remaining"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"~{hours}h {minutes}m remaining"

    def get_step_estimate(self, step_name: str) -> float:
        """Get estimated duration for a single step.

        Args:
            step_name: Name of the step.

        Returns:
            Estimated duration in seconds.
        """
        avg = self.store.get_average(self.workflow_name, step_name)
        return avg if avg is not None else self.default_step_duration
