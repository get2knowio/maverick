"""Integration tests for hierarchical step_path on events.

These tests verify that when the executor runs a workflow, events
receive correct step_path values reflecting the nesting hierarchy.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    AgentStreamChunk,
    LoopIterationCompleted,
    LoopIterationStarted,
    ProgressEvent,
    StepCompleted,
    StepStarted,
)
from maverick.dsl.serialization import ComponentRegistry, WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow


class TestExecutorStepPaths:
    """Integration tests for step_path propagation through execution."""

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

        return reg

    @pytest.mark.asyncio
    async def test_top_level_steps_have_step_path(
        self, registry: ComponentRegistry
    ) -> None:
        """Top-level steps get step_path equal to their name."""
        workflow_yaml = """
version: "1.0"
name: test-paths
description: Test step paths

steps:
  - name: step_a
    type: python
    action: str_upper
    kwargs:
      value: hello

  - name: step_b
    type: python
    action: double
    kwargs:
      n: 5
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)

        events: list[ProgressEvent] = []
        async for event in executor.execute(workflow, {}):
            events.append(event)

        # Find StepStarted/Completed for step_a and step_b
        started_a = [
            e for e in events if isinstance(e, StepStarted) and e.step_name == "step_a"
        ]
        completed_a = [
            e
            for e in events
            if isinstance(e, StepCompleted) and e.step_name == "step_a"
        ]
        started_b = [
            e for e in events if isinstance(e, StepStarted) and e.step_name == "step_b"
        ]

        assert len(started_a) == 1
        assert started_a[0].step_path == "step_a"

        assert len(completed_a) == 1
        assert completed_a[0].step_path == "step_a"

        assert len(started_b) == 1
        assert started_b[0].step_path == "step_b"

    @pytest.mark.asyncio
    async def test_loop_iteration_events_have_step_path(
        self, registry: ComponentRegistry
    ) -> None:
        """Loop iteration events get [N] path segments."""
        workflow_yaml = """
version: "1.0"
name: test-loop-paths
description: Test loop step paths

inputs:
  items:
    type: array
    required: true

steps:
  - name: my_loop
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
        executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)

        events: list[ProgressEvent] = []
        async for event in executor.execute(workflow, {"items": ["a", "b"]}):
            events.append(event)

        # LoopIterationStarted events should have step_path
        iter_started = [e for e in events if isinstance(e, LoopIterationStarted)]
        assert len(iter_started) == 2

        # Iteration events get [N] path from the loop handler
        # then the executor's callback wrapper prepends "my_loop"
        assert iter_started[0].step_path == "my_loop/[0]"
        assert iter_started[1].step_path == "my_loop/[1]"

        # LoopIterationCompleted events should also have step_path
        iter_completed = [e for e in events if isinstance(e, LoopIterationCompleted)]
        assert len(iter_completed) == 2
        completed_paths = {e.step_path for e in iter_completed}
        assert "my_loop/[0]" in completed_paths
        assert "my_loop/[1]" in completed_paths

    @pytest.mark.asyncio
    async def test_stream_callback_inside_loop_has_nested_path(
        self, registry: ComponentRegistry
    ) -> None:
        """AgentStreamChunk events via stream_callback get full nested paths."""
        from collections.abc import Awaitable, Callable

        streamed_chunks: list[AgentStreamChunk] = []

        @registry.actions.register("emit_output")
        async def emit_output(
            value: str,
            stream_callback: Callable[[str], Awaitable[None]] | None = None,
        ) -> str:
            if stream_callback:
                await stream_callback(f"Processing {value}")
            return value.upper()

        workflow_yaml = """
version: "1.0"
name: test-nested-paths
description: Test nested step paths

inputs:
  items:
    type: array
    required: true

steps:
  - name: my_loop
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: emit_step
        type: python
        action: emit_output
        kwargs:
          value: ${{ item }}
"""
        workflow = parse_workflow(workflow_yaml)
        executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)

        events: list[ProgressEvent] = []
        async for event in executor.execute(workflow, {"items": ["x", "y"]}):
            events.append(event)
            if isinstance(event, AgentStreamChunk):
                streamed_chunks.append(event)

        # AgentStreamChunk events should have nested path from callback chain:
        # my_loop wraps callback -> [N] wraps callback -> emit_step wraps callback
        # The stream_to_event creates AgentStreamChunk without step_path,
        # then emit_step prefix, [N] prefix, my_loop prefix are applied
        assert len(streamed_chunks) == 2

        chunk_paths = {e.step_path for e in streamed_chunks}
        assert "my_loop/[0]/emit_step" in chunk_paths
        assert "my_loop/[1]/emit_step" in chunk_paths
