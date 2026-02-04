"""Tests for step_path utilities."""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    AgentStreamChunk,
    StepCompleted,
    StepOutput,
    StepStarted,
    WorkflowStarted,
)
from maverick.dsl.serialization.executor.step_path import (
    build_path,
    make_prefix_callback,
)
from maverick.dsl.types import StepType


class TestBuildPath:
    """Tests for build_path()."""

    def test_none_prefix(self) -> None:
        assert build_path(None, "step_a") == "step_a"

    def test_with_prefix(self) -> None:
        assert build_path("step_a", "[0]") == "step_a/[0]"

    def test_nested(self) -> None:
        assert build_path("step_a/[0]", "validate") == "step_a/[0]/validate"

    def test_empty_prefix(self) -> None:
        # Empty string is falsy, treated like None
        assert build_path("", "step_a") == "step_a"


class TestMakePrefixCallback:
    """Tests for make_prefix_callback()."""

    @pytest.mark.anyio
    async def test_prefix_prepended_to_step_started(self) -> None:
        """Verify prefix is prepended to events with step_path."""
        received: list[object] = []

        async def inner(event: object) -> None:
            received.append(event)

        callback = make_prefix_callback("my_loop", inner)

        event = StepStarted(
            step_name="child_step",
            step_type=StepType.PYTHON,
            step_path="child_step",
        )
        await callback(event)

        assert len(received) == 1
        result = received[0]
        assert isinstance(result, StepStarted)
        assert result.step_path == "my_loop/child_step"

    @pytest.mark.anyio
    async def test_prefix_on_event_with_no_existing_path(self) -> None:
        """When step_path is None, prefix becomes the path."""
        received: list[object] = []

        async def inner(event: object) -> None:
            received.append(event)

        callback = make_prefix_callback("outer", inner)

        event = StepOutput(
            step_name="inner",
            message="hello",
        )
        await callback(event)

        assert len(received) == 1
        result = received[0]
        assert isinstance(result, StepOutput)
        assert result.step_path == "outer"

    @pytest.mark.anyio
    async def test_nested_prefixing(self) -> None:
        """Nested callbacks compose paths correctly."""
        received: list[object] = []

        async def inner(event: object) -> None:
            received.append(event)

        outer_cb = make_prefix_callback("loop", inner)
        mid_cb = make_prefix_callback("[0]", outer_cb)
        leaf_cb = make_prefix_callback("validate", mid_cb)

        event = AgentStreamChunk(
            step_name="agent",
            agent_name="TestAgent",
            text="hi",
            chunk_type="output",
            step_path="agent",
        )
        await leaf_cb(event)

        assert len(received) == 1
        result = received[0]
        assert isinstance(result, AgentStreamChunk)
        assert result.step_path == "loop/[0]/validate/agent"

    @pytest.mark.anyio
    async def test_events_without_step_path_pass_through(self) -> None:
        """Events without step_path attribute pass through unchanged."""
        received: list[object] = []

        async def inner(event: object) -> None:
            received.append(event)

        callback = make_prefix_callback("my_step", inner)

        event = WorkflowStarted(
            workflow_name="test",
            inputs={},
        )
        await callback(event)

        assert len(received) == 1
        result = received[0]
        assert isinstance(result, WorkflowStarted)
        # WorkflowStarted has no step_path
        assert not hasattr(result, "step_path")

    @pytest.mark.anyio
    async def test_step_completed_with_prefix(self) -> None:
        """StepCompleted events get prefix applied."""
        received: list[object] = []

        async def inner(event: object) -> None:
            received.append(event)

        callback = make_prefix_callback("parent", inner)

        event = StepCompleted(
            step_name="child",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=100,
            step_path="child",
        )
        await callback(event)

        result = received[0]
        assert isinstance(result, StepCompleted)
        assert result.step_path == "parent/child"
