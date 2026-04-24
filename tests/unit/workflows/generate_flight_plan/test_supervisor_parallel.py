"""Tests for parallel briefing fan-out in PlanSupervisor.

The class-under-test is ``PlanSupervisor._run_briefing_parallel``. This
method dispatches three specialist briefing agents concurrently via
``asyncio.gather``. A regression that re-serialized the loop would go
undetected by functional tests, so we assert on wall-clock timing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import patch

import pytest

from maverick.workflows.fly_beads.actors.protocol import Message, MessageType
from maverick.workflows.generate_flight_plan.supervisor import PlanSupervisor


class _SlowActor:
    """Actor stub whose ``receive`` sleeps for a configurable duration."""

    def __init__(self, agent_name: str, tool_name: str, delay: float) -> None:
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.delay = delay
        self.started_at: float | None = None

    async def receive(self, msg: Message) -> list[Message]:
        self.started_at = time.perf_counter()
        await asyncio.sleep(self.delay)
        return [
            Message(
                msg_type=MessageType.BRIEFING_RESULT,
                sender=self.agent_name,
                recipient="supervisor",
                payload={
                    "tool": self.tool_name,
                    "result": {},
                },
            )
        ]


class TestBriefingParallelism:
    @pytest.mark.asyncio
    async def test_briefing_agents_dispatched_concurrently(self) -> None:
        """All three briefing agents should start within a small window.

        If the dispatch were serialized, the third agent's start time
        would be ~2x delay after the first. Parallel dispatch starts
        all three within a fraction of the delay.
        """
        delay = 0.3
        actors: dict[str, Any] = {
            "scopist": _SlowActor("scopist", "submit_scope", delay),
            "codebase_analyst": _SlowActor("codebase_analyst", "submit_analysis", delay),
            "criteria_writer": _SlowActor("criteria_writer", "submit_criteria", delay),
        }

        supervisor = PlanSupervisor(
            actors=actors,
            prd_content="test prd",
            plan_name="test",
        )

        # Stub the parser so we don't need full payload schema
        with patch(
            "maverick.workflows.generate_flight_plan.supervisor.parse_supervisor_tool_payload",
            return_value={},
        ):
            # Stub the prompt builder import so we don't pull heavy deps
            with patch(
                "maverick.agents.preflight_briefing.prompts.build_preflight_briefing_prompt",
                return_value="briefing prompt",
            ):
                t0 = time.perf_counter()
                await supervisor._run_briefing_parallel()
                elapsed = time.perf_counter() - t0

        # Wall clock: parallel ≈ delay, sequential ≈ 3 * delay
        assert elapsed < delay * 2, (
            f"briefing took {elapsed:.2f}s; expected <{delay * 2}s (parallel)"
        )

        # Start times: all three within a tight window (much less than delay)
        start_times = [
            actor.started_at
            for actor in actors.values()
            if isinstance(actor, _SlowActor) and actor.started_at is not None
        ]
        assert len(start_times) == 3
        spread = max(start_times) - min(start_times)
        assert spread < delay / 2, (
            f"briefing actors started over a {spread:.3f}s window; "
            f"expected <{delay / 2:.3f}s (concurrent dispatch)"
        )

    @pytest.mark.asyncio
    async def test_one_failing_agent_does_not_sink_others(self) -> None:
        """An exception from one actor should be logged, others still recorded."""

        class _BrokenActor:
            async def receive(self, msg: Message) -> list[Message]:
                raise RuntimeError("boom")

        actors: dict[str, Any] = {
            "scopist": _BrokenActor(),
            "codebase_analyst": _SlowActor("codebase_analyst", "submit_analysis", 0.05),
            "criteria_writer": _SlowActor("criteria_writer", "submit_criteria", 0.05),
        }

        supervisor = PlanSupervisor(
            actors=actors,
            prd_content="test prd",
            plan_name="test",
        )

        with patch(
            "maverick.workflows.generate_flight_plan.supervisor.parse_supervisor_tool_payload",
            return_value={},
        ):
            with patch(
                "maverick.agents.preflight_briefing.prompts.build_preflight_briefing_prompt",
                return_value="briefing prompt",
            ):
                await supervisor._run_briefing_parallel()

        # scopist failed; the two working actors should have produced briefs
        assert "scopist" not in supervisor._briefs
        assert "codebase_analyst" in supervisor._briefs
        assert "criteria_writer" in supervisor._briefs
