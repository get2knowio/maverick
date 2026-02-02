"""Unit tests for the prerequisite runner."""

from __future__ import annotations

import asyncio

import pytest

from maverick.dsl.events import (
    PreflightCheckFailed,
    PreflightCheckPassed,
    PreflightCompleted,
    PreflightStarted,
)
from maverick.dsl.prerequisites.models import (
    PreflightPlan,
    PrerequisiteResult,
)
from maverick.dsl.prerequisites.registry import PrerequisiteRegistry
from maverick.dsl.prerequisites.runner import PrerequisiteRunner


@pytest.fixture
def registry() -> PrerequisiteRegistry:
    """Create a prerequisite registry with test checks."""
    reg = PrerequisiteRegistry()

    @reg.register(name="fast_check", display_name="Fast Check")
    async def check_fast() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="Fast check passed")

    @reg.register(name="slow_check", display_name="Slow Check")
    async def check_slow() -> PrerequisiteResult:
        await asyncio.sleep(0.01)
        return PrerequisiteResult(success=True, message="Slow check passed")

    @reg.register(
        name="failing_check", display_name="Failing Check", remediation="Fix it"
    )
    async def check_failing() -> PrerequisiteResult:
        return PrerequisiteResult(success=False, message="This check always fails")

    @reg.register(name="base", display_name="Base Check")
    async def check_base() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="Base OK")

    @reg.register(
        name="dependent", display_name="Dependent Check", dependencies=("base",)
    )
    async def check_dependent() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="Dependent OK")

    @reg.register(name="failing_base", display_name="Failing Base")
    async def check_failing_base() -> PrerequisiteResult:
        return PrerequisiteResult(success=False, message="Base failed")

    @reg.register(
        name="depends_on_failing",
        display_name="Depends on Failing",
        dependencies=("failing_base",),
    )
    async def check_depends_on_failing() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="Should never run")

    @reg.register(name="exception_check", display_name="Exception Check")
    async def check_exception() -> PrerequisiteResult:
        raise RuntimeError("Something went wrong")

    return reg


class TestPrerequisiteRunner:
    """Tests for PrerequisiteRunner."""

    @pytest.mark.asyncio
    async def test_run_empty_plan(self, registry: PrerequisiteRegistry) -> None:
        """Test running an empty plan returns success."""
        plan = PreflightPlan(
            prerequisites=(),
            step_requirements={},
            execution_order=(),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is True
        assert result.check_results == ()
        assert result.total_duration_ms == 0

    @pytest.mark.asyncio
    async def test_run_single_check_success(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test running a single successful check."""
        plan = PreflightPlan(
            prerequisites=("fast_check",),
            step_requirements={"fast_check": ("step1",)},
            execution_order=("fast_check",),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is True
        assert len(result.check_results) == 1
        assert result.check_results[0].result.success is True
        assert result.check_results[0].result.message == "Fast check passed"
        assert result.check_results[0].affected_steps == ("step1",)

    @pytest.mark.asyncio
    async def test_run_single_check_failure(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test running a single failing check."""
        plan = PreflightPlan(
            prerequisites=("failing_check",),
            step_requirements={"failing_check": ("step1", "step2")},
            execution_order=("failing_check",),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is False
        assert len(result.check_results) == 1
        assert result.check_results[0].result.success is False
        assert "always fails" in result.check_results[0].result.message
        assert result.check_results[0].affected_steps == ("step1", "step2")

    @pytest.mark.asyncio
    async def test_run_multiple_checks_success(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test running multiple successful checks."""
        plan = PreflightPlan(
            prerequisites=("fast_check", "slow_check"),
            step_requirements={
                "fast_check": ("step1",),
                "slow_check": ("step2",),
            },
            execution_order=("fast_check", "slow_check"),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is True
        assert len(result.check_results) == 2
        assert all(cr.result.success for cr in result.check_results)
        assert result.total_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_dependency_order(self, registry: PrerequisiteRegistry) -> None:
        """Test checks run in dependency order (base before dependent)."""
        plan = PreflightPlan(
            prerequisites=("base", "dependent"),
            step_requirements={
                "base": ("step1",),
                "dependent": ("step1",),
            },
            execution_order=("base", "dependent"),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is True
        assert len(result.check_results) == 2
        # Verify order matches execution_order
        assert result.check_results[0].prerequisite.name == "base"
        assert result.check_results[1].prerequisite.name == "dependent"

    @pytest.mark.asyncio
    async def test_run_dependency_failure_skips_dependents(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test that dependent checks are skipped when dependency fails."""
        plan = PreflightPlan(
            prerequisites=("failing_base", "depends_on_failing"),
            step_requirements={
                "failing_base": ("step1",),
                "depends_on_failing": ("step1",),
            },
            execution_order=("failing_base", "depends_on_failing"),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is False
        assert len(result.check_results) == 2

        # First check failed
        assert result.check_results[0].result.success is False
        assert "Base failed" in result.check_results[0].result.message

        # Second check was skipped
        assert result.check_results[1].result.success is False
        assert "Skipped" in result.check_results[1].result.message
        assert "failing_base" in result.check_results[1].result.message

    @pytest.mark.asyncio
    async def test_run_check_timeout(self, registry: PrerequisiteRegistry) -> None:
        """Test that checks timeout correctly."""

        # Register a slow check that will timeout
        @registry.register(name="very_slow", display_name="Very Slow")
        async def check_very_slow() -> PrerequisiteResult:
            await asyncio.sleep(10)  # Sleep for 10 seconds
            return PrerequisiteResult(success=True, message="OK")

        plan = PreflightPlan(
            prerequisites=("very_slow",),
            step_requirements={"very_slow": ("step1",)},
            execution_order=("very_slow",),
        )

        # Use short timeout
        runner = PrerequisiteRunner(registry, timeout_per_check=0.05)
        result = await runner.run(plan)

        assert result.success is False
        assert len(result.check_results) == 1
        assert result.check_results[0].result.success is False
        assert "timed out" in result.check_results[0].result.message

    @pytest.mark.asyncio
    async def test_run_check_exception(self, registry: PrerequisiteRegistry) -> None:
        """Test that check exceptions are handled gracefully."""
        plan = PreflightPlan(
            prerequisites=("exception_check",),
            step_requirements={"exception_check": ("step1",)},
            execution_order=("exception_check",),
        )

        runner = PrerequisiteRunner(registry)
        result = await runner.run(plan)

        assert result.success is False
        assert len(result.check_results) == 1
        assert result.check_results[0].result.success is False
        assert "error" in result.check_results[0].result.message.lower()
        assert "Something went wrong" in result.check_results[0].result.message


class TestPrerequisiteRunnerWithEvents:
    """Tests for PrerequisiteRunner.run_with_events()."""

    @pytest.mark.asyncio
    async def test_run_with_events_empty_plan(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test events for empty plan."""
        plan = PreflightPlan(
            prerequisites=(),
            step_requirements={},
            execution_order=(),
        )

        runner = PrerequisiteRunner(registry)
        events = [event async for event in runner.run_with_events(plan)]

        assert len(events) == 2
        assert isinstance(events[0], PreflightStarted)
        assert events[0].prerequisites == ()
        assert isinstance(events[1], PreflightCompleted)
        assert events[1].success is True
        assert events[1].passed_count == 0
        assert events[1].failed_count == 0

    @pytest.mark.asyncio
    async def test_run_with_events_success(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test events for successful run."""
        plan = PreflightPlan(
            prerequisites=("fast_check",),
            step_requirements={"fast_check": ("step1",)},
            execution_order=("fast_check",),
        )

        runner = PrerequisiteRunner(registry)
        events = [event async for event in runner.run_with_events(plan)]

        assert (
            len(events) == 3
        )  # PreflightStarted, PreflightCheckPassed, PreflightCompleted

        assert isinstance(events[0], PreflightStarted)
        assert events[0].prerequisites == ("fast_check",)

        assert isinstance(events[1], PreflightCheckPassed)
        assert events[1].name == "fast_check"
        assert events[1].display_name == "Fast Check"
        assert "passed" in events[1].message.lower()

        assert isinstance(events[2], PreflightCompleted)
        assert events[2].success is True
        assert events[2].passed_count == 1
        assert events[2].failed_count == 0

    @pytest.mark.asyncio
    async def test_run_with_events_failure(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test events for failed run."""
        plan = PreflightPlan(
            prerequisites=("failing_check",),
            step_requirements={"failing_check": ("step1", "step2")},
            execution_order=("failing_check",),
        )

        runner = PrerequisiteRunner(registry)
        events = [event async for event in runner.run_with_events(plan)]

        assert len(events) == 3

        assert isinstance(events[0], PreflightStarted)

        assert isinstance(events[1], PreflightCheckFailed)
        assert events[1].name == "failing_check"
        assert events[1].display_name == "Failing Check"
        assert "fails" in events[1].message.lower()
        assert events[1].remediation == "Fix it"
        assert events[1].affected_steps == ("step1", "step2")

        assert isinstance(events[2], PreflightCompleted)
        assert events[2].success is False
        assert events[2].passed_count == 0
        assert events[2].failed_count == 1

    @pytest.mark.asyncio
    async def test_run_with_events_mixed(self, registry: PrerequisiteRegistry) -> None:
        """Test events for mixed pass/fail run."""
        plan = PreflightPlan(
            prerequisites=("fast_check", "failing_check"),
            step_requirements={
                "fast_check": ("step1",),
                "failing_check": ("step2",),
            },
            execution_order=("fast_check", "failing_check"),
        )

        runner = PrerequisiteRunner(registry)
        events = [event async for event in runner.run_with_events(plan)]

        assert len(events) == 4  # Started, Passed, Failed, Completed

        assert isinstance(events[0], PreflightStarted)
        assert events[0].prerequisites == ("fast_check", "failing_check")

        assert isinstance(events[1], PreflightCheckPassed)
        assert events[1].name == "fast_check"

        assert isinstance(events[2], PreflightCheckFailed)
        assert events[2].name == "failing_check"

        assert isinstance(events[3], PreflightCompleted)
        assert events[3].success is False
        assert events[3].passed_count == 1
        assert events[3].failed_count == 1

    @pytest.mark.asyncio
    async def test_run_with_events_skipped_dependent(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test events when dependent is skipped due to failed dependency."""
        plan = PreflightPlan(
            prerequisites=("failing_base", "depends_on_failing"),
            step_requirements={
                "failing_base": ("step1",),
                "depends_on_failing": ("step1",),
            },
            execution_order=("failing_base", "depends_on_failing"),
        )

        runner = PrerequisiteRunner(registry)
        events = [event async for event in runner.run_with_events(plan)]

        assert len(events) == 4

        # First check failed
        assert isinstance(events[1], PreflightCheckFailed)
        assert events[1].name == "failing_base"

        # Second check was skipped (also reported as failed)
        assert isinstance(events[2], PreflightCheckFailed)
        assert events[2].name == "depends_on_failing"
        assert "Skipped" in events[2].message

        # Final result
        assert isinstance(events[3], PreflightCompleted)
        assert events[3].success is False
        assert events[3].failed_count == 2
