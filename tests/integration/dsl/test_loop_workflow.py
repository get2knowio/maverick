"""Integration tests for parallel workflow execution with YAML files.

These tests verify end-to-end parallel step execution with the WorkflowFileExecutor,
testing both basic parallel execution and for_each iteration.
"""

from __future__ import annotations

import pytest

from maverick.dsl.serialization import (
    ComponentRegistry,
    WorkflowFileExecutor,
)
from maverick.dsl.serialization.parser import parse_workflow


class TestParallelWorkflowExecution:
    """Integration tests for parallel step execution from YAML workflows."""

    @pytest.mark.asyncio
    async def test_parallel_for_each_yaml_workflow(self) -> None:
        """Test executing a YAML workflow with parallel for_each iteration.

        This test verifies:
        - Parsing YAML with parallel step and for_each
        - Evaluating for_each expression to get iteration list
        - Creating isolated contexts for each iteration
        - Executing steps concurrently for each item
        - Aggregating results from all iterations
        """
        yaml_content = """
version: "1.0"
name: parallel-processing
description: Process items in parallel using for_each

inputs:
  items:
    type: array
    description: Items to process

steps:
  - name: process_all_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process_item
        type: python
        action: process_item
        kwargs:
          value: ${{ item }}
"""

        # Create registry with test action
        registry = ComponentRegistry()

        @registry.actions.register("process_item")
        async def process_item(value):
            return f"processed_{value}"

        # Parse workflow
        workflow = parse_workflow(yaml_content)

        # Verify schema is correct
        assert workflow.name == "parallel-processing"
        assert len(workflow.steps) == 1
        loop_step = workflow.steps[0]
        assert loop_step.type.value == "loop"
        assert loop_step.for_each == "${{ inputs.items }}"
        assert len(loop_step.steps) == 1

        # Execute workflow
        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(
            workflow, inputs={"items": ["apple", "banana", "cherry"]}
        ):
            events.append(event)

        # Verify result
        result = executor.get_result()
        assert result.success is True
        assert isinstance(result.final_output, list)
        assert len(result.final_output) == 3

        # Each iteration should have results from its step
        for iteration_result in result.final_output:
            assert isinstance(iteration_result, (list, tuple))
            assert len(iteration_result) == 1

    @pytest.mark.asyncio
    async def test_parallel_for_each_multiple_steps_yaml(self) -> None:
        """Test parallel for_each with multiple steps per iteration."""
        yaml_content = """
version: "1.0"
name: multi-step-parallel
description: Execute multiple steps per iteration

inputs:
  numbers:
    type: array

steps:
  - name: process_numbers
    type: loop
    for_each: ${{ inputs.numbers }}
    steps:
      - name: double
        type: python
        action: double_value
        kwargs:
          n: ${{ item }}
      - name: square
        type: python
        action: square_value
        kwargs:
          n: ${{ item }}
"""

        registry = ComponentRegistry()

        @registry.actions.register("double_value")
        def double_value(n):
            return n * 2

        @registry.actions.register("square_value")
        def square_value(n):
            return n**2

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow, inputs={"numbers": [2, 3, 4]}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output) == 3

        # Each iteration has 2 steps
        for iteration_result in result.final_output:
            assert len(iteration_result) == 2

    @pytest.mark.asyncio
    async def test_parallel_for_each_with_subsequent_step(self) -> None:
        """Test parallel for_each followed by aggregation step."""
        yaml_content = """
version: "1.0"
name: parallel-with-aggregation
description: Process items then aggregate results

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: transform
        type: python
        action: transform_item
        kwargs:
          item: ${{ item }}

  - name: check_completion
    type: python
    action: mark_complete
"""

        registry = ComponentRegistry()

        @registry.actions.register("transform_item")
        async def transform_item(item):
            return item.upper()

        @registry.actions.register("mark_complete")
        def mark_complete():
            return "completed"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        items = ["a", "b", "c", "d"]
        async for _ in executor.execute(workflow, inputs={"items": items}):
            pass

        result = executor.get_result()
        assert result.success is True
        # First step output contains parallel results
        assert result.step_results[0].output
        assert len(result.step_results[0].output) == 4
        # Final output is from the check_completion step
        assert result.final_output == "completed"

    @pytest.mark.asyncio
    async def test_parallel_without_for_each_yaml(self) -> None:
        """Test parallel step without for_each (basic parallel execution)."""
        yaml_content = """
version: "1.0"
name: basic-parallel
description: Execute steps in parallel without iteration

steps:
  - name: run_parallel
    type: loop
    steps:
      - name: task_a
        type: python
        action: task_a
      - name: task_b
        type: python
        action: task_b
      - name: task_c
        type: python
        action: task_c
"""

        registry = ComponentRegistry()

        @registry.actions.register("task_a")
        async def task_a():
            return "A"

        @registry.actions.register("task_b")
        async def task_b():
            return "B"

        @registry.actions.register("task_c")
        async def task_c():
            return "C"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output) == 3
        assert "A" in result.final_output
        assert "B" in result.final_output
        assert "C" in result.final_output

    @pytest.mark.asyncio
    async def test_parallel_for_each_empty_list_yaml(self) -> None:
        """Test parallel for_each with empty list."""
        yaml_content = """
version: "1.0"
name: empty-parallel
description: Handle empty iteration list

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process
        type: python
        action: process_item
        kwargs:
          item: ${{ item }}
"""

        registry = ComponentRegistry()

        @registry.actions.register("process_item")
        def process_item(item):
            return item

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow, inputs={"items": []}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == []

    @pytest.mark.asyncio
    async def test_parallel_for_each_with_partial_failure_yaml(self) -> None:
        """Test parallel for_each with one iteration failing.

        When any iteration in a loop step fails, the entire loop step should fail
        and propagate the error to stop the workflow. This ensures that failures
        are not silently swallowed.
        """
        yaml_content = """
version: "1.0"
name: parallel-with-errors
description: Handle failures in parallel iterations

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: maybe_fail
        type: python
        action: maybe_fail
        kwargs:
          value: ${{ item }}
"""

        registry = ComponentRegistry()

        @registry.actions.register("maybe_fail")
        async def maybe_fail(value):
            if value == "error":
                raise ValueError("Intentional failure")
            return f"ok_{value}"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(
            workflow, inputs={"items": ["good1", "error", "good2"]}
        ):
            pass

        result = executor.get_result()
        # Loop step should fail when any iteration fails
        assert result.success is False

        # Check that the step result indicates failure
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.name == "process_items"
        assert step_result.success is False
        assert step_result.error is not None
        assert "Intentional failure" in step_result.error

    @pytest.mark.asyncio
    async def test_for_each_stops_on_first_failure(self) -> None:
        """Test that sequential for_each stops after the first failure.

        With max_concurrency=1 (default), iterations run sequentially.
        When an iteration fails, subsequent iterations must NOT execute.
        """
        yaml_content = """
version: "1.0"
name: fail-fast-sequential
description: Stop on first failure

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 1
    steps:
      - name: track_and_maybe_fail
        type: python
        action: track_and_maybe_fail
        kwargs:
          value: ${{ item }}
"""

        executed: list[str] = []
        registry = ComponentRegistry()

        @registry.actions.register("track_and_maybe_fail")
        async def track_and_maybe_fail(value):
            executed.append(value)
            if value == "fail":
                raise ValueError("Intentional failure")
            return f"ok_{value}"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(
            workflow, inputs={"items": ["a", "b", "fail", "c", "d"]}
        ):
            pass

        result = executor.get_result()
        assert result.success is False

        # Items after "fail" must NOT have been executed
        assert "a" in executed
        assert "b" in executed
        assert "fail" in executed
        assert "c" not in executed
        assert "d" not in executed

    @pytest.mark.asyncio
    async def test_loop_tasks_stop_on_first_failure(self) -> None:
        """Test that sequential loop tasks stop after the first failure.

        Non-for_each loop with max_concurrency=1 should also stop on
        first task failure.
        """
        yaml_content = """
version: "1.0"
name: fail-fast-tasks

steps:
  - name: run_tasks
    type: loop
    max_concurrency: 1
    steps:
      - name: task_ok
        type: python
        action: task_ok
      - name: task_fail
        type: python
        action: task_fail
      - name: task_after
        type: python
        action: task_after
"""

        executed: list[str] = []
        registry = ComponentRegistry()

        @registry.actions.register("task_ok")
        async def task_ok():
            executed.append("task_ok")
            return "ok"

        @registry.actions.register("task_fail")
        async def task_fail():
            executed.append("task_fail")
            raise ValueError("Task failed")

        @registry.actions.register("task_after")
        async def task_after():
            executed.append("task_after")
            return "after"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False

        # task_after must NOT have executed
        assert "task_ok" in executed
        assert "task_fail" in executed
        assert "task_after" not in executed

    @pytest.mark.asyncio
    async def test_failure_stops_subsequent_step(self) -> None:
        """Test that a failed loop step prevents subsequent workflow steps.

        When a loop step fails, the entire workflow should stop —
        no subsequent top-level steps should execute.
        """
        yaml_content = """
version: "1.0"
name: fail-stops-workflow

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: maybe_fail
        type: python
        action: maybe_fail
        kwargs:
          value: ${{ item }}

  - name: should_not_run
    type: python
    action: should_not_run
"""

        executed: list[str] = []
        registry = ComponentRegistry()

        @registry.actions.register("maybe_fail")
        async def maybe_fail(value):
            executed.append(f"process_{value}")
            if value == "bad":
                raise ValueError("Intentional failure")
            return f"ok_{value}"

        @registry.actions.register("should_not_run")
        async def should_not_run():
            executed.append("should_not_run")
            return "ran"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow, inputs={"items": ["good", "bad"]}):
            pass

        result = executor.get_result()
        assert result.success is False

        # The step after the failed loop must NOT execute
        assert "should_not_run" not in executed


class TestParallelWorkflowEdgeCases:
    """Edge case tests for parallel workflow execution."""

    @pytest.mark.asyncio
    async def test_parallel_for_each_nested_data_yaml(self) -> None:
        """Test parallel for_each with nested data structures."""
        yaml_content = """
version: "1.0"
name: nested-data-parallel
description: Process nested data in parallel

inputs:
  users:
    type: array

steps:
  - name: process_users
    type: loop
    for_each: ${{ inputs.users }}
    steps:
      - name: extract_name
        type: python
        action: get_name
        kwargs:
          user: ${{ item }}
"""

        registry = ComponentRegistry()

        @registry.actions.register("get_name")
        def get_name(user):
            return user.get("name", "unknown")

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        users_data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]

        async for _ in executor.execute(workflow, inputs={"users": users_data}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output) == 3


class TestParallelShorthand:
    """Tests for the parallel: true/false shorthand in loop steps."""

    @pytest.mark.asyncio
    async def test_parallel_true_enables_concurrent_execution(self) -> None:
        """Test that parallel: true enables unlimited concurrent execution.

        When parallel: true is set, all tasks should be able to run
        concurrently (equivalent to max_concurrency: 0).
        """
        yaml_content = """
version: "1.0"
name: parallel-shorthand
description: Use parallel shorthand for concurrency

steps:
  - name: run_tasks
    type: loop
    parallel: true
    steps:
      - name: task_a
        type: python
        action: task_a
      - name: task_b
        type: python
        action: task_b
      - name: task_c
        type: python
        action: task_c
"""

        import time

        start_times: list[float] = []
        registry = ComponentRegistry()

        @registry.actions.register("task_a")
        async def task_a():
            start_times.append(time.time())
            return "A"

        @registry.actions.register("task_b")
        async def task_b():
            start_times.append(time.time())
            return "B"

        @registry.actions.register("task_c")
        async def task_c():
            start_times.append(time.time())
            return "C"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output) == 3
        # All tasks should have started nearly simultaneously (within 0.5 seconds)
        # This verifies concurrent execution
        assert len(start_times) == 3
        time_span = max(start_times) - min(start_times)
        assert time_span < 0.5, f"Tasks started too far apart: {time_span}s"

    @pytest.mark.asyncio
    async def test_parallel_false_enables_sequential_execution(self) -> None:
        """Test that parallel: false ensures sequential execution.

        When parallel: false is set, tasks should run one at a time
        (equivalent to max_concurrency: 1).
        """
        yaml_content = """
version: "1.0"
name: sequential-shorthand
description: "Use parallel: false for sequential execution"

steps:
  - name: run_tasks
    type: loop
    parallel: false
    steps:
      - name: task_a
        type: python
        action: task_a
      - name: task_b
        type: python
        action: task_b
"""

        execution_order: list[str] = []
        registry = ComponentRegistry()

        @registry.actions.register("task_a")
        async def task_a():
            execution_order.append("a_start")
            execution_order.append("a_end")
            return "A"

        @registry.actions.register("task_b")
        async def task_b():
            execution_order.append("b_start")
            execution_order.append("b_end")
            return "B"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Sequential execution means task_a completes before task_b starts
        assert execution_order == ["a_start", "a_end", "b_start", "b_end"]

    @pytest.mark.asyncio
    async def test_parallel_true_with_for_each(self) -> None:
        """Test parallel: true with for_each iteration.

        All iterations should run concurrently.
        """
        yaml_content = """
version: "1.0"
name: parallel-for-each
description: Parallel iteration with for_each

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    parallel: true
    steps:
      - name: process
        type: python
        action: process_item
        kwargs:
          item: ${{ item }}
"""

        registry = ComponentRegistry()
        processed: list[str] = []

        @registry.actions.register("process_item")
        async def process_item(item):
            processed.append(item)
            return f"processed_{item}"

        workflow = parse_workflow(yaml_content)
        executor = WorkflowFileExecutor(registry=registry)

        async for _ in executor.execute(
            workflow, inputs={"items": ["a", "b", "c", "d"]}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output) == 4
        # All items should be processed
        assert set(processed) == {"a", "b", "c", "d"}

    @pytest.mark.asyncio
    async def test_yaml_roundtrip_with_parallel(self) -> None:
        """Test that parallel field survives YAML round-trip."""
        yaml_content = """
version: "1.0"
name: roundtrip-test
description: Test YAML round-trip with parallel

steps:
  - name: parallel_tasks
    type: loop
    parallel: true
    steps:
      - name: task1
        type: python
        action: task1
"""

        # Parse the original
        workflow = parse_workflow(yaml_content)
        loop_step = workflow.steps[0]
        assert loop_step.parallel is True
        assert loop_step.get_effective_max_concurrency() == 0

        # Convert to YAML and back
        yaml_output = workflow.to_yaml()
        workflow_roundtrip = parse_workflow(yaml_output)

        # Verify the parallel field survived
        loop_step_rt = workflow_roundtrip.steps[0]
        assert loop_step_rt.parallel is True
        assert loop_step_rt.get_effective_max_concurrency() == 0

    @pytest.mark.asyncio
    async def test_yaml_roundtrip_with_parallel_false(self) -> None:
        """Test that parallel: false survives YAML round-trip."""
        yaml_content = """
version: "1.0"
name: roundtrip-test-false
description: Test YAML round-trip with parallel false

steps:
  - name: sequential_tasks
    type: loop
    parallel: false
    steps:
      - name: task1
        type: python
        action: task1
"""

        # Parse the original
        workflow = parse_workflow(yaml_content)
        loop_step = workflow.steps[0]
        assert loop_step.parallel is False
        assert loop_step.get_effective_max_concurrency() == 1

        # Convert to YAML and back
        yaml_output = workflow.to_yaml()
        workflow_roundtrip = parse_workflow(yaml_output)

        # Verify the parallel field survived
        loop_step_rt = workflow_roundtrip.steps[0]
        assert loop_step_rt.parallel is False
        assert loop_step_rt.get_effective_max_concurrency() == 1
