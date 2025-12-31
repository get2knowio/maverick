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
    type: parallel
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
        parallel_step = workflow.steps[0]
        assert parallel_step.type.value == "parallel"
        assert parallel_step.for_each == "${{ inputs.items }}"
        assert len(parallel_step.steps) == 1

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
        assert "results" in result.final_output
        assert len(result.final_output["results"]) == 3

        # Each iteration should have results from its step
        for iteration_result in result.final_output["results"]:
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
    type: parallel
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
        assert len(result.final_output["results"]) == 3

        # Each iteration has 2 steps
        for iteration_result in result.final_output["results"]:
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
    type: parallel
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
        assert result.step_results[0].output["results"]
        assert len(result.step_results[0].output["results"]) == 4
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
    type: parallel
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
        assert len(result.final_output["results"]) == 3
        assert "A" in result.final_output["results"]
        assert "B" in result.final_output["results"]
        assert "C" in result.final_output["results"]

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
    type: parallel
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
        assert result.final_output["results"] == []

    @pytest.mark.asyncio
    async def test_parallel_for_each_with_partial_failure_yaml(self) -> None:
        """Test parallel for_each with one iteration failing."""
        yaml_content = """
version: "1.0"
name: parallel-with-errors
description: Handle failures in parallel iterations

inputs:
  items:
    type: array

steps:
  - name: process_items
    type: parallel
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
        # Parallel step uses return_exceptions=True, so it completes
        assert result.success is True
        assert len(result.final_output["results"]) == 3

        # Check that one iteration has an exception
        has_exception = False
        for iteration_result in result.final_output["results"]:
            if isinstance(iteration_result, Exception):
                has_exception = True
                break
            # Check nested results
            for step_result in iteration_result:
                if isinstance(step_result, Exception):
                    has_exception = True
                    break
        assert has_exception


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
    type: parallel
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
        assert len(result.final_output["results"]) == 3
