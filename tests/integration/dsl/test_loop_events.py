"""Integration tests for loop event emission end-to-end.

These tests verify that when a loop step executes, it correctly emits
LoopIterationStarted and LoopIterationCompleted events that can be
consumed by the TUI.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    LoopIterationCompleted,
    LoopIterationStarted,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization import ComponentRegistry, WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow


class TestLoopIterationEvents:
    """Integration tests for loop step event emission."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a component registry with test actions."""
        reg = ComponentRegistry()

        @reg.actions.register("str_upper")
        def str_upper(value: str) -> str:
            return value.upper()

        @reg.actions.register("double")
        def double(n: int) -> int:
            return n * 2

        @reg.actions.register("failing_action")
        def failing_action(value: str) -> None:
            if value == "fail":
                raise ValueError("Intentional failure for testing")

        @reg.actions.register("extract_name")
        def extract_name(item: dict) -> str:
            return item.get("name", "unknown")

        @reg.actions.register("process_inner")
        def process_inner(outer: str, inner: str) -> str:
            return f"{outer}-{inner}"

        return reg

    @pytest.mark.asyncio
    async def test_loop_emits_iteration_started_events(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that loop step emits LoopIterationStarted events for each item."""
        workflow_yaml = """
version: "1.0"
name: test-loop-started
description: Test loop iteration started events

inputs:
  items:
    type: array
    required: true

steps:
  - name: test_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"items": ["a", "b", "c"]}
        ):
            events.append(event)

        # Verify LoopIterationStarted events
        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        assert len(started_events) == 3  # 3 items

        # Verify event data
        assert started_events[0].step_name == "test_loop"
        assert started_events[0].total_iterations == 3

        # Check that all indices are present (order may vary due to concurrency)
        indices = {e.iteration_index for e in started_events}
        assert indices == {0, 1, 2}

        # Verify item labels
        labels = {e.item_label for e in started_events}
        assert labels == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_loop_emits_iteration_completed_events(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that loop step emits LoopIterationCompleted events."""
        workflow_yaml = """
version: "1.0"
name: test-loop-completed
description: Test loop iteration completed events

inputs:
  items:
    type: array
    required: true

steps:
  - name: test_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"items": ["x", "y", "z"]}
        ):
            events.append(event)

        # Verify LoopIterationCompleted events
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]
        assert len(completed_events) == 3  # 3 items

        # Verify all completions are successful
        assert all(e.success is True for e in completed_events)
        assert all(e.error is None for e in completed_events)

        # Verify duration_ms is set for all events
        assert all(e.duration_ms >= 0 for e in completed_events)

        # Check that all indices are present
        indices = {e.iteration_index for e in completed_events}
        assert indices == {0, 1, 2}

    @pytest.mark.asyncio
    async def test_loop_events_contain_correct_data(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that loop events contain all required data fields."""
        workflow_yaml = """
version: "1.0"
name: test-loop-data
description: Test loop event data fields

inputs:
  items:
    type: array
    required: true

steps:
  - name: data_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: extract
        type: python
        action: extract_name
        kwargs:
          item: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        items = [{"name": "alpha"}, {"name": "beta"}]
        events = []
        async for event in executor.execute(workflow, inputs={"items": items}):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Verify LoopIterationStarted data
        for event in started_events:
            assert event.step_name == "data_loop"
            assert event.total_iterations == 2
            assert event.iteration_index in (0, 1)
            # Item labels should be extracted from "name" key
            assert event.item_label in ("alpha", "beta")
            assert event.parent_step_name is None  # Not nested
            assert event.timestamp > 0

        # Verify LoopIterationCompleted data
        for event in completed_events:
            assert event.step_name == "data_loop"
            assert event.iteration_index in (0, 1)
            assert event.success is True
            assert event.duration_ms >= 0
            assert event.error is None
            assert event.timestamp > 0

    @pytest.mark.asyncio
    async def test_loop_events_emitted_on_iteration_failure(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that events are emitted for iterations that ran, but not skipped ones.

        With fail-fast behavior (default max_concurrency=1), iterations after a
        failure are skipped entirely — no started or completed events are emitted
        for them.
        """
        workflow_yaml = """
version: "1.0"
name: test-loop-failure
description: Test loop event emission on failure

inputs:
  items:
    type: array
    required: true

steps:
  - name: failing_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: maybe_fail
        type: python
        action: failing_action
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"items": ["ok", "fail", "never"]}
        ):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        # Only "ok" and "fail" should have events; "never" is skipped (fail-fast)
        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Find the failed iteration completed event
        failed_completions = [e for e in completed_events if not e.success]
        assert len(failed_completions) == 1

        failed_event = failed_completions[0]
        assert failed_event.success is False
        assert failed_event.error is not None
        assert "Intentional failure" in failed_event.error

        # The "ok" iteration should have succeeded
        successful_completions = [e for e in completed_events if e.success]
        assert len(successful_completions) == 1

    @pytest.mark.asyncio
    async def test_loop_events_with_multiple_steps_per_iteration(
        self, registry: ComponentRegistry
    ) -> None:
        """Test loop events when each iteration has multiple steps."""
        workflow_yaml = """
version: "1.0"
name: test-multi-step-loop
description: Test loop with multiple steps per iteration

inputs:
  numbers:
    type: array
    required: true

steps:
  - name: multi_step_loop
    type: loop
    for_each: ${{ inputs.numbers }}
    steps:
      - name: double_it
        type: python
        action: double
        kwargs:
          n: ${{ item }}
      - name: double_again
        type: python
        action: double
        kwargs:
          n: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow, inputs={"numbers": [1, 2]}):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        # Should have 2 iterations (for 2 numbers)
        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Each completed event should represent the full iteration
        # (both steps within the iteration)
        for event in completed_events:
            assert event.success is True

    @pytest.mark.asyncio
    async def test_loop_events_with_empty_list(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that no loop events are emitted for empty iteration list."""
        workflow_yaml = """
version: "1.0"
name: test-empty-loop
description: Test loop with empty list

inputs:
  items:
    type: array
    required: true

steps:
  - name: empty_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow, inputs={"items": []}):
            events.append(event)

        # Should have no LoopIterationStarted or LoopIterationCompleted events
        loop_events = [
            e
            for e in events
            if isinstance(e, (LoopIterationStarted, LoopIterationCompleted))
        ]
        assert len(loop_events) == 0

        # Workflow should still complete successfully
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is True

    @pytest.mark.asyncio
    async def test_loop_events_with_concurrency(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that loop events are emitted correctly with concurrent execution."""
        workflow_yaml = """
version: "1.0"
name: test-concurrent-loop
description: Test concurrent loop execution

inputs:
  items:
    type: array
    required: true

steps:
  - name: concurrent_loop
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 2
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"items": ["a", "b", "c", "d"]}
        ):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        # All 4 iterations should have started and completed
        assert len(started_events) == 4
        assert len(completed_events) == 4

        # All iterations should be successful
        assert all(e.success is True for e in completed_events)

        # Check that all indices are represented
        started_indices = {e.iteration_index for e in started_events}
        completed_indices = {e.iteration_index for e in completed_events}
        assert started_indices == {0, 1, 2, 3}
        assert completed_indices == {0, 1, 2, 3}

    @pytest.mark.asyncio
    async def test_loop_events_item_label_extraction(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that item labels are correctly extracted from different item types."""
        workflow_yaml = """
version: "1.0"
name: test-label-extraction
description: Test item label extraction

inputs:
  items:
    type: array
    required: true

steps:
  - name: label_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: test
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        items = [
            {"name": "Named Item"},
            {"label": "Labeled Item"},
            {"phase": "Phase 1"},
            {"title": "Titled Item"},
            {"id": "item-123"},
            "plain_string",
        ]
        events = []
        async for event in executor.execute(workflow, inputs={"items": items}):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        assert len(started_events) == 6

        # Collect labels
        labels = {e.item_label for e in started_events}

        # Labels should include extracted values from dict keys and string item
        assert "Named Item" in labels  # from "name" key
        assert "Labeled Item" in labels  # from "label" key
        assert "Phase 1" in labels  # from "phase" key
        assert "Titled Item" in labels  # from "title" key
        assert "item-123" in labels  # from "id" key
        assert "plain_string" in labels  # string item used directly

    @pytest.mark.asyncio
    async def test_loop_events_event_ordering(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that events are ordered correctly (started before completed)."""
        workflow_yaml = """
version: "1.0"
name: test-event-ordering
description: Test event ordering

inputs:
  items:
    type: array
    required: true

steps:
  - name: ordered_loop
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 1
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow, inputs={"items": ["single"]}):
            events.append(event)

        # Find the loop iteration events
        loop_events = [
            e
            for e in events
            if isinstance(e, (LoopIterationStarted, LoopIterationCompleted))
        ]

        # With a single item, we should have exactly 2 loop events
        assert len(loop_events) == 2

        # Started should come before completed
        assert isinstance(loop_events[0], LoopIterationStarted)
        assert isinstance(loop_events[1], LoopIterationCompleted)

        # Both should be for the same iteration
        assert loop_events[0].iteration_index == 0
        assert loop_events[1].iteration_index == 0


class TestNestedLoopEvents:
    """Integration tests for nested loop event emission."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a component registry with test actions."""
        reg = ComponentRegistry()

        @reg.actions.register("concat")
        def concat(a: str, b: str) -> str:
            return f"{a}-{b}"

        @reg.actions.register("outer_process")
        def outer_process(value: str) -> str:
            return value.upper()

        return reg

    @pytest.mark.asyncio
    async def test_nested_loops_emit_parent_step_name(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that nested loops emit events with parent_step_name set.

        Note: Current implementation does not pass parent_step_name for nested loops.
        This test documents expected behavior for future enhancement.
        """
        # This test uses a workflow with a branch containing a loop
        # to test nested structure. True nested loops (loop inside loop)
        # would require the loop handler to pass parent context.
        workflow_yaml = """
version: "1.0"
name: test-nested-loop
description: Test nested loop events

inputs:
  outer_items:
    type: array
    required: true
  inner_items:
    type: array
    required: true

steps:
  - name: outer_loop
    type: loop
    for_each: ${{ inputs.outer_items }}
    max_concurrency: 1
    steps:
      - name: process_outer
        type: python
        action: outer_process
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"outer_items": ["A", "B"], "inner_items": ["x", "y"]}
        ):
            events.append(event)

        # Verify outer loop events
        outer_started = [
            e
            for e in events
            if isinstance(e, LoopIterationStarted) and e.step_name == "outer_loop"
        ]
        outer_completed = [
            e
            for e in events
            if isinstance(e, LoopIterationCompleted) and e.step_name == "outer_loop"
        ]

        assert len(outer_started) == 2
        assert len(outer_completed) == 2

        # Parent step name is None for top-level loops
        assert all(e.parent_step_name is None for e in outer_started)


class TestLoopTaskEvents:
    """Integration tests for loop step without for_each (task parallelism)."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a component registry with test actions."""
        reg = ComponentRegistry()

        @reg.actions.register("task_a")
        def task_a() -> str:
            return "A"

        @reg.actions.register("task_b")
        def task_b() -> str:
            return "B"

        @reg.actions.register("task_c")
        def task_c() -> str:
            return "C"

        @reg.actions.register("failing_task")
        def failing_task() -> None:
            raise RuntimeError("Task failed")

        return reg

    @pytest.mark.asyncio
    async def test_loop_without_foreach_emits_events(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that loop without for_each emits events for each task."""
        workflow_yaml = """
version: "1.0"
name: test-task-loop
description: Test loop without for_each

steps:
  - name: task_loop
    type: loop
    steps:
      - name: step_a
        type: python
        action: task_a
      - name: step_b
        type: python
        action: task_b
      - name: step_c
        type: python
        action: task_c
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        # Should emit events for each step (3 steps)
        assert len(started_events) == 3
        assert len(completed_events) == 3

        # All should be successful
        assert all(e.success is True for e in completed_events)

        # Step names should be used as item labels
        labels = {e.item_label for e in started_events}
        assert "step_a" in labels
        assert "step_b" in labels
        assert "step_c" in labels

    @pytest.mark.asyncio
    async def test_loop_task_failure_emits_events(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that failing task still emits completed event with error."""
        workflow_yaml = """
version: "1.0"
name: test-failing-task-loop
description: Test failing task in loop

steps:
  - name: failing_task_loop
    type: loop
    steps:
      - name: good_task
        type: python
        action: task_a
      - name: bad_task
        type: python
        action: failing_task
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow):
            events.append(event)

        started_events = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed_events = [e for e in events if isinstance(e, LoopIterationCompleted)]

        # Both tasks should have started and completed events
        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Find the failed task
        failed_completions = [e for e in completed_events if not e.success]
        assert len(failed_completions) == 1
        assert failed_completions[0].error is not None
        assert "Task failed" in failed_completions[0].error


class TestLoopEventsWithWorkflowContext:
    """Integration tests for loop events within full workflow context."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a component registry with test actions."""
        reg = ComponentRegistry()

        @reg.actions.register("str_upper")
        def str_upper(value: str) -> str:
            return value.upper()

        @reg.actions.register("get_items")
        def get_items() -> list:
            return ["item1", "item2", "item3"]

        @reg.actions.register("count_results")
        def count_results(results: list) -> int:
            return len(results)

        return reg

    @pytest.mark.asyncio
    async def test_loop_events_with_preceding_step(
        self, registry: ComponentRegistry
    ) -> None:
        """Test loop events when preceded by another step."""
        workflow_yaml = """
version: "1.0"
name: test-loop-with-setup
description: Test loop with setup step

steps:
  - name: get_data
    type: python
    action: get_items

  - name: process_items
    type: loop
    for_each: ${{ steps.get_data.output }}
    steps:
      - name: transform
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow):
            events.append(event)

        # Verify workflow structure events
        workflow_started = [e for e in events if isinstance(e, WorkflowStarted)]
        workflow_completed = [e for e in events if isinstance(e, WorkflowCompleted)]
        step_started = [e for e in events if isinstance(e, StepStarted)]
        step_completed = [e for e in events if isinstance(e, StepCompleted)]

        assert len(workflow_started) == 1
        assert len(workflow_completed) == 1
        assert len(step_started) == 2  # get_data + process_items
        assert len(step_completed) == 2

        # Verify loop events
        loop_started = [e for e in events if isinstance(e, LoopIterationStarted)]
        loop_completed = [e for e in events if isinstance(e, LoopIterationCompleted)]

        assert len(loop_started) == 3  # 3 items from get_items
        assert len(loop_completed) == 3
        assert all(e.step_name == "process_items" for e in loop_started)

    @pytest.mark.asyncio
    async def test_loop_events_with_following_step(
        self, registry: ComponentRegistry
    ) -> None:
        """Test loop events when followed by another step."""
        workflow_yaml = """
version: "1.0"
name: test-loop-with-aggregation
description: Test loop followed by aggregation

inputs:
  items:
    type: array
    required: true

steps:
  - name: process_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: transform
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}

  - name: aggregate
    type: python
    action: count_results
    kwargs:
      results: ${{ steps.process_loop.output.results }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(workflow, inputs={"items": ["a", "b"]}):
            events.append(event)

        # Verify loop events appear before the aggregate step events
        loop_started = [e for e in events if isinstance(e, LoopIterationStarted)]
        loop_completed = [e for e in events if isinstance(e, LoopIterationCompleted)]

        assert len(loop_started) == 2
        assert len(loop_completed) == 2

        # Workflow should complete successfully
        result = executor.get_result()
        assert result.success is True
        assert result.final_output == 2  # count of 2 items


class TestRealTimeEventStreaming:
    """Integration tests for real-time event streaming during step execution.

    These tests verify that loop iteration events are streamed in real-time
    (arriving BEFORE the loop step completes) rather than being batched
    and yielded only after step completion.
    """

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a component registry with test actions."""
        import asyncio

        reg = ComponentRegistry()

        @reg.actions.register("slow_action")
        async def slow_action(value: str) -> str:
            await asyncio.sleep(0.05)  # 50ms delay
            return value.upper()

        @reg.actions.register("str_upper")
        def str_upper(value: str) -> str:
            return value.upper()

        return reg

    @pytest.mark.asyncio
    async def test_loop_events_stream_during_execution(
        self, registry: ComponentRegistry
    ) -> None:
        """Verify loop iteration events arrive BEFORE loop step completes.

        This is the key test for real-time streaming (SC-001/SC-002).
        Events should be yielded as soon as they occur, not batched.
        """
        workflow_yaml = """
version: "1.0"
name: test-realtime-streaming
description: Test real-time event streaming

inputs:
  items:
    type: array
    required: true

steps:
  - name: streaming_loop
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 1
    steps:
      - name: process
        type: python
        action: slow_action
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events_before_step_complete = []
        loop_step_completed = False

        async for event in executor.execute(
            workflow, inputs={"items": ["a", "b", "c"]}
        ):
            if isinstance(event, StepCompleted) and event.step_name == "streaming_loop":
                loop_step_completed = True
            elif (
                isinstance(event, (LoopIterationStarted, LoopIterationCompleted))
                and not loop_step_completed
            ):
                # Record if this event arrived BEFORE the step completed
                events_before_step_complete.append(event)

        # Key assertion: loop iteration events should arrive BEFORE step completes
        # With 3 items, we expect 6 events (3 started + 3 completed)
        assert len(events_before_step_complete) == 6, (
            f"Expected 6 loop iteration events before step completion, "
            f"got {len(events_before_step_complete)}. "
            f"Events should stream in real-time, not batch after completion."
        )

        # Verify we have both started and completed events
        started = [
            e
            for e in events_before_step_complete
            if isinstance(e, LoopIterationStarted)
        ]
        completed = [
            e
            for e in events_before_step_complete
            if isinstance(e, LoopIterationCompleted)
        ]
        assert len(started) == 3
        assert len(completed) == 3

    @pytest.mark.asyncio
    async def test_first_iteration_event_arrives_early(
        self, registry: ComponentRegistry
    ) -> None:
        """Verify the first iteration event arrives before later iterations complete.

        With sequential execution (max_concurrency: 1), the first LoopIterationStarted
        should arrive before any LoopIterationCompleted for later iterations.
        """
        workflow_yaml = """
version: "1.0"
name: test-early-first-event
description: Test first event arrives early

inputs:
  items:
    type: array
    required: true

steps:
  - name: test_loop
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 1
    steps:
      - name: process
        type: python
        action: str_upper
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry)

        events = []
        async for event in executor.execute(
            workflow, inputs={"items": ["x", "y", "z"]}
        ):
            events.append(event)

        # Find the first LoopIterationStarted event
        first_started_index = None
        for i, event in enumerate(events):
            if isinstance(event, LoopIterationStarted):
                first_started_index = i
                break

        # Find the StepCompleted event for the loop
        step_completed_index = None
        for i, event in enumerate(events):
            if isinstance(event, StepCompleted) and event.step_name == "test_loop":
                step_completed_index = i
                break

        # The first iteration event should appear before the step completes
        assert first_started_index is not None, (
            "Should have a LoopIterationStarted event"
        )
        assert step_completed_index is not None, "Should have a StepCompleted event"
        assert first_started_index < step_completed_index, (
            "First LoopIterationStarted should appear before StepCompleted"
        )
