"""Integration tests for WorkflowEngine with flow control."""

from __future__ import annotations

import pytest

from maverick.dsl import WorkflowEngine, WorkflowError, step, workflow
from maverick.dsl.checkpoint.store import MemoryCheckpointStore
from maverick.dsl.errors import InputMismatchError
from maverick.exceptions import DuplicateStepNameError


class TestEngineFlowControl:
    """Integration tests for flow control in WorkflowEngine."""

    # T053a: workflow raises WorkflowError
    @pytest.mark.asyncio
    async def test_workflow_error_fails_workflow(self) -> None:
        """Workflow should fail when WorkflowError is raised."""

        @workflow(name="error_wf")
        def error_workflow():
            raise WorkflowError("Something went wrong")
            yield step("never").python(action=lambda: "never")

        engine = WorkflowEngine()

        # WorkflowError should propagate from execute()
        with pytest.raises(WorkflowError) as exc_info:
            async for _ in engine.execute(error_workflow):
                pass

        # Verify the error message
        assert exc_info.value.reason == "Something went wrong"

    # T078: workflow resumes from checkpoint
    @pytest.mark.asyncio
    async def test_workflow_resumes_from_checkpoint(self) -> None:
        """Workflow should resume from saved checkpoint."""
        store = MemoryCheckpointStore()
        counter_tracker = {"value": 1}

        @workflow(name="resumable")
        def resumable_workflow(counter: int):
            r1 = yield step("step1").checkpoint().python(action=lambda: "s1")
            r2 = yield step("step2").python(
                action=lambda: f"s2-{counter_tracker['value']}"
            )
            return {"r1": r1, "r2": r2}

        # First run with counter=1
        engine1 = WorkflowEngine(checkpoint_store=store)
        events1 = []
        async for event in engine1.execute(
            resumable_workflow, workflow_id="test-run", counter=1
        ):
            events1.append(event)

        result1 = engine1.get_result()
        assert result1.success is True
        assert result1.final_output == {"r1": "s1", "r2": "s2-1"}

        # Update counter tracker for second run
        counter_tracker["value"] = 2

        # Resume with same inputs (counter=1)
        engine2 = WorkflowEngine(checkpoint_store=store)
        events2 = []
        async for event in engine2.resume(
            resumable_workflow, workflow_id="test-run", counter=1
        ):
            events2.append(event)

        result2 = engine2.get_result()
        assert result2.success is True
        # step1 should be restored from checkpoint (s1)
        # step2 should execute with new counter value (s2-2)
        assert result2.final_output == {"r1": "s1", "r2": "s2-2"}

        # Verify step1 was not re-executed (only step2 appears in new events)
        from maverick.dsl import StepStarted

        step_started_events = [e for e in events2 if isinstance(e, StepStarted)]
        step_names = [e.step_name for e in step_started_events]
        assert "step2" in step_names
        # step1 should not be in started events (it was restored)
        assert "step1" not in step_names

    # T079: resume fails on input mismatch
    @pytest.mark.asyncio
    async def test_resume_fails_on_input_mismatch(self) -> None:
        """Resume should fail if inputs don't match checkpoint."""
        store = MemoryCheckpointStore()

        @workflow(name="input_check")
        def input_check_workflow(x: int):
            r1 = yield step("step1").checkpoint().python(action=lambda: "result1")
            return r1

        # Create checkpoint with x=1
        engine1 = WorkflowEngine(checkpoint_store=store)
        async for _ in engine1.execute(
            input_check_workflow, workflow_id="test-run", x=1
        ):
            pass

        result1 = engine1.get_result()
        assert result1.success is True

        # Try to resume with different inputs (x=2)
        engine2 = WorkflowEngine(checkpoint_store=store)

        with pytest.raises(InputMismatchError) as exc_info:
            async for _ in engine2.resume(
                input_check_workflow, workflow_id="test-run", x=2
            ):
                pass

        # Verify the error contains hash information
        assert exc_info.value.expected_hash is not None
        assert exc_info.value.actual_hash is not None
        assert exc_info.value.expected_hash != exc_info.value.actual_hash

    # T080: full flow control integration
    @pytest.mark.asyncio
    async def test_full_flow_control_integration(self) -> None:
        """Test conditions + retry + rollback + checkpoint together."""
        from maverick.dsl import SkipMarker

        store = MemoryCheckpointStore()
        retry_counter = {"attempts": 0}
        rollback_executed = {"value": False}

        def rollback_action(ctx):
            rollback_executed["value"] = True

        def retry_action():
            retry_counter["attempts"] += 1
            if retry_counter["attempts"] < 2:
                raise ValueError("First attempt fails")
            return "retry-success"

        @workflow(name="full_flow")
        def full_flow_workflow(skip_conditional: bool):
            # Conditional step (skip if condition false)
            r1 = yield step("conditional").when(lambda ctx: not skip_conditional).python(
                action=lambda: "conditional-ran"
            )

            # Step with retry (succeeds on 2nd attempt)
            r2 = yield step("retry").retry(max_attempts=3, backoff=0.01).python(
                action=retry_action
            )

            # Step with rollback registered
            r3 = yield step("with_rollback").with_rollback(rollback_action).python(
                action=lambda: "rollback-registered"
            )

            # Checkpoint step
            r4 = yield step("checkpoint").checkpoint().python(action=lambda: "cp-done")

            return {"r1": r1, "r2": r2, "r3": r3, "r4": r4}

        # Execute with skip_conditional=False (conditional should run)
        engine = WorkflowEngine(checkpoint_store=store)
        events = []
        async for event in engine.execute(
            full_flow_workflow, workflow_id="test-run", skip_conditional=False
        ):
            events.append(event)

        result = engine.get_result()
        assert result.success is True
        # Conditional ran
        assert result.final_output["r1"] == "conditional-ran"
        # Retry succeeded
        assert result.final_output["r2"] == "retry-success"
        assert retry_counter["attempts"] == 2
        # Rollback registered but not executed (workflow succeeded)
        assert rollback_executed["value"] is False
        assert result.final_output["r3"] == "rollback-registered"
        # Checkpoint completed
        assert result.final_output["r4"] == "cp-done"

        # Test with skip_conditional=True (conditional should be skipped)
        retry_counter["attempts"] = 0
        engine2 = WorkflowEngine(checkpoint_store=store)
        events2 = []
        async for event in engine2.execute(
            full_flow_workflow, workflow_id="test-run-2", skip_conditional=True
        ):
            events2.append(event)

        result2 = engine2.get_result()
        assert result2.success is True
        # Conditional was skipped
        assert isinstance(result2.final_output["r1"], SkipMarker)
        assert result2.final_output["r1"].reason == "predicate_false"
        # Other steps still executed
        assert result2.final_output["r2"] == "retry-success"
        assert result2.final_output["r3"] == "rollback-registered"
        assert result2.final_output["r4"] == "cp-done"

    # T080a: duplicate step names in loop
    @pytest.mark.asyncio
    async def test_duplicate_step_names_fails(self) -> None:
        """Engine should fail on duplicate step names."""

        @workflow(name="dup_wf")
        def duplicate_workflow():
            for i in range(3):
                yield step("same_name").python(action=lambda: i)

        engine = WorkflowEngine()

        with pytest.raises(DuplicateStepNameError) as exc_info:
            async for _ in engine.execute(duplicate_workflow):
                pass

        # Verify the error contains the duplicate step name
        assert exc_info.value.step_name == "same_name"
