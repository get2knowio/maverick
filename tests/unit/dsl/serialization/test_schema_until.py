"""Unit tests for LoopStepRecord until loop schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.dsl.serialization.schema import LoopStepRecord, PythonStepRecord
from maverick.dsl.types import StepType


def _make_python_step(name: str = "body") -> PythonStepRecord:
    return PythonStepRecord(name=name, type=StepType.PYTHON, action="noop")


class TestUntilForEachMutuallyExclusive:
    """Tests for until and for_each mutual exclusion."""

    def test_until_only_is_valid(self) -> None:
        step = LoopStepRecord(
            name="loop",
            type=StepType.LOOP,
            until="${{ steps.check.output.done }}",
            steps=[_make_python_step()],
        )
        assert step.until is not None
        assert step.for_each is None

    def test_for_each_only_is_valid(self) -> None:
        step = LoopStepRecord(
            name="loop",
            type=StepType.LOOP,
            for_each="${{ steps.items.output }}",
            steps=[_make_python_step()],
        )
        assert step.for_each is not None
        assert step.until is None

    def test_both_until_and_for_each_rejected(self) -> None:
        with pytest.raises(ValidationError, match="until.*for_each"):
            LoopStepRecord(
                name="loop",
                type=StepType.LOOP,
                until="${{ steps.check.output.done }}",
                for_each="${{ steps.items.output }}",
                steps=[_make_python_step()],
            )


class TestUntilParallelMutuallyExclusive:
    """Tests for until and parallel mutual exclusion."""

    def test_until_with_parallel_true_rejected(self) -> None:
        with pytest.raises(ValidationError, match="parallel.*until"):
            LoopStepRecord(
                name="loop",
                type=StepType.LOOP,
                until="${{ steps.check.output.done }}",
                parallel=True,
                steps=[_make_python_step()],
            )

    def test_until_with_parallel_false_is_valid(self) -> None:
        """parallel: false just means sequential, which is fine for until."""
        step = LoopStepRecord(
            name="loop",
            type=StepType.LOOP,
            until="${{ steps.check.output.done }}",
            parallel=False,
            steps=[_make_python_step()],
        )
        assert step.until is not None
        assert step.parallel is False


class TestMaxIterations:
    """Tests for max_iterations field."""

    def test_default_max_iterations(self) -> None:
        step = LoopStepRecord(
            name="loop",
            type=StepType.LOOP,
            until="${{ steps.check.output.done }}",
            steps=[_make_python_step()],
        )
        assert step.max_iterations == 30

    def test_custom_max_iterations(self) -> None:
        step = LoopStepRecord(
            name="loop",
            type=StepType.LOOP,
            until="${{ steps.check.output.done }}",
            max_iterations=5,
            steps=[_make_python_step()],
        )
        assert step.max_iterations == 5

    def test_zero_max_iterations_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_iterations"):
            LoopStepRecord(
                name="loop",
                type=StepType.LOOP,
                until="${{ steps.check.output.done }}",
                max_iterations=0,
                steps=[_make_python_step()],
            )


class TestYamlRoundtrip:
    """Tests for YAML serialization roundtrip."""

    def test_until_loop_roundtrip(self) -> None:
        from maverick.dsl.serialization.schema import WorkflowFile

        yaml_content = """
version: "1.0"
name: test-until
description: Test until loop

inputs:
  max_loops:
    type: integer
    required: false
    default: 10

steps:
  - name: my_loop
    type: loop
    until: ${{ steps.check.output.done }}
    max_iterations: 15
    steps:
      - name: process
        type: python
        action: noop
      - name: check
        type: python
        action: check_done
"""
        wf = WorkflowFile.from_yaml(yaml_content)

        assert len(wf.steps) == 1
        loop_step = wf.steps[0]
        assert isinstance(loop_step, LoopStepRecord)
        assert loop_step.until == "${{ steps.check.output.done }}"
        assert loop_step.max_iterations == 15
        assert loop_step.for_each is None
        assert len(loop_step.steps) == 2

        # Roundtrip
        yaml_out = wf.to_yaml()
        wf2 = WorkflowFile.from_yaml(yaml_out)
        loop2 = wf2.steps[0]
        assert isinstance(loop2, LoopStepRecord)
        assert loop2.until == loop_step.until
        assert loop2.max_iterations == loop_step.max_iterations
