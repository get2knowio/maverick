"""Dry-run mode tests for FlyWorkflow (T090a, T090c).

These tests verify that dry-run mode:
1. Emits progress events
2. Does NOT execute git operations
3. Does NOT invoke agents
4. Does NOT create PRs
5. Emits same event sequence as real runs
"""

from __future__ import annotations

import pytest

from maverick.workflows.fly import (
    FlyInputs,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflow,
    FlyWorkflowCompleted,
    FlyWorkflowStarted,
)


class TestFlyWorkflowDryRun:
    """Tests for FlyWorkflow dry-run mode (T090a, T090c)."""

    @pytest.mark.asyncio
    async def test_dry_run_emits_progress_events(self, tmp_path):
        """Test FlyWorkflow dry-run mode emits progress events (T090a)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test-branch", error=None, duration_ms=50
            )
        )
        mock_git.diff = AsyncMock(return_value="test diff")
        mock_git.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit", error=None, duration_ms=50
            )
        )
        mock_git.add = AsyncMock(return_value=None)

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock(return_value="https://github.com/test/pr/1")

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file, dry_run=True)

        # Execute and collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify workflow started event
        started_events = [e for e in events if isinstance(e, FlyWorkflowStarted)]
        assert len(started_events) == 1
        assert started_events[0].inputs.dry_run is True

        # Verify stage events were emitted
        stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
        stage_completed = [e for e in events if isinstance(e, FlyStageCompleted)]

        # Should have at least INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW stages
        assert len(stage_started) >= 4
        assert len(stage_completed) >= 4

        # Verify workflow completed
        completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
        assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_dry_run_does_not_execute_git_operations(self, tmp_path):
        """Test FlyWorkflow dry-run mode does not execute git operations (T090a)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock()
        mock_git.add = AsyncMock()
        mock_git.commit = AsyncMock()
        mock_git.diff = AsyncMock(return_value="")

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify git operations were NOT called in dry-run mode
        mock_git.create_branch_with_fallback.assert_not_called()
        mock_git.add.assert_not_called()
        mock_git.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_create_pr(self, tmp_path):
        """Test FlyWorkflow dry-run mode does not create PR (T090a)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock()
        mock_git.add = AsyncMock()
        mock_git.commit = AsyncMock()
        mock_git.diff = AsyncMock(return_value="")

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock()

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify GitHub PR creation was NOT called
        mock_github.create_pr.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_invoke_agents(self, tmp_path):
        """Test FlyWorkflow dry-run mode does not invoke agents (T090a)."""
        from unittest.mock import AsyncMock, MagicMock

        # Setup mocks
        mock_git = MagicMock()
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock()
        mock_validation = MagicMock()
        mock_validation.run = AsyncMock()
        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock()
        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock()
        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock()

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify agents were NOT invoked in dry-run mode
        mock_agent.execute.assert_not_called()
        mock_validation.run.assert_not_called()
        mock_reviewer.execute.assert_not_called()
        mock_commit_gen.generate.assert_not_called()
        mock_pr_gen.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_event_sequence_matches_real_run(self, tmp_path):
        """Test FlyWorkflow dry-run emits same event types as real run (T090c)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup mocks for real run
        mock_git_real = MagicMock()
        mock_git_real.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )
        mock_git_real.diff = AsyncMock(return_value="diff")
        mock_git_real.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit", error=None, duration_ms=50
            )
        )
        mock_git_real.add = AsyncMock()

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent_real = MagicMock()
        mock_agent_real.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation_real = MagicMock()
        mock_validation_real.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer_real = MagicMock()
        mock_reviewer_real.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen_real = MagicMock()
        mock_commit_gen_real.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen_real = MagicMock()
        mock_pr_gen_real.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github_real = MagicMock()
        mock_github_real.create_pr = AsyncMock(
            return_value="https://github.com/test/pr/1"
        )

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        # Execute real run
        workflow_real = FlyWorkflow(
            git_runner=mock_git_real,
            implementer_agent=mock_agent_real,
            validation_runner=mock_validation_real,
            code_reviewer_agent=mock_reviewer_real,
            commit_generator=mock_commit_gen_real,
            pr_generator=mock_pr_gen_real,
            github_runner=mock_github_real,
        )
        inputs_real = FlyInputs(branch_name="test", task_file=task_file, dry_run=False)

        real_events = []
        async for event in workflow_real.execute(inputs_real):
            real_events.append(event)

        # Setup mocks for dry run
        mock_git_dry = MagicMock()
        mock_agent_dry = MagicMock()
        mock_validation_dry = MagicMock()
        mock_reviewer_dry = MagicMock()
        mock_commit_gen_dry = MagicMock()
        mock_pr_gen_dry = MagicMock()
        mock_github_dry = MagicMock()

        # Execute dry run
        workflow_dry = FlyWorkflow(
            git_runner=mock_git_dry,
            implementer_agent=mock_agent_dry,
            validation_runner=mock_validation_dry,
            code_reviewer_agent=mock_reviewer_dry,
            commit_generator=mock_commit_gen_dry,
            pr_generator=mock_pr_gen_dry,
            github_runner=mock_github_dry,
        )
        inputs_dry = FlyInputs(branch_name="test", task_file=task_file, dry_run=True)

        dry_events = []
        async for event in workflow_dry.execute(inputs_dry):
            dry_events.append(event)

        # Extract event type sequences
        real_event_types = [type(e).__name__ for e in real_events]
        dry_event_types = [type(e).__name__ for e in dry_events]

        # Verify same event types in same order
        assert real_event_types == dry_event_types, (
            f"Event sequences differ:\nReal: {real_event_types}\nDry: {dry_event_types}"
        )

        # Verify both have started event
        assert any(isinstance(e, FlyWorkflowStarted) for e in real_events)
        assert any(isinstance(e, FlyWorkflowStarted) for e in dry_events)

        # Verify both have completed event
        assert any(isinstance(e, FlyWorkflowCompleted) for e in real_events)
        assert any(isinstance(e, FlyWorkflowCompleted) for e in dry_events)
