"""Dry-run mode tests for RefuelWorkflow (T090b).

These tests verify that dry-run mode:
1. Emits progress events
2. Does NOT execute git operations
3. Does NOT invoke agents
4. Does NOT create branches or PRs
5. Emits same event sequence as real runs
"""

from __future__ import annotations

import pytest

from maverick.workflows.refuel import (
    IssueProcessingCompleted,
    IssueProcessingStarted,
    RefuelCompleted,
    RefuelConfig,
    RefuelInputs,
    RefuelStarted,
    RefuelWorkflow,
)


class TestRefuelWorkflowDryRun:
    """Tests for RefuelWorkflow dry-run mode (T090b)."""

    @pytest.mark.asyncio
    async def test_dry_run_emits_progress_events(self):
        """Test RefuelWorkflow dry-run mode emits progress events (T090b)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner
        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Fix bug 1",
                    body="Bug description 1",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
                RunnerGitHubIssue(
                    number=2,
                    title="Fix bug 2",
                    body="Bug description 2",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/2",
                ),
            ]
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=5, dry_run=True)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify RefuelStarted event
        started_events = [e for e in events if isinstance(e, RefuelStarted)]
        assert len(started_events) == 1
        assert started_events[0].inputs.dry_run is True
        assert started_events[0].issues_found == 2

        # Verify issue processing events
        processing_started = [
            e for e in events if isinstance(e, IssueProcessingStarted)
        ]
        processing_completed = [
            e for e in events if isinstance(e, IssueProcessingCompleted)
        ]

        assert len(processing_started) == 2
        assert len(processing_completed) == 2

        # Verify RefuelCompleted event
        completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
        assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_dry_run_does_not_execute_git_operations(self):
        """Test RefuelWorkflow dry-run mode does not execute git operations (T090b)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitRunner
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock runners
        mock_git = MagicMock(spec=GitRunner)
        mock_git.create_branch = AsyncMock()
        mock_git.add = AsyncMock()
        mock_git.commit = AsyncMock()

        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=123,
                    title="Fix auth",
                    body="Auth bug",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/123",
                ),
            ]
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            git_runner=mock_git,
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=1, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify git operations were NOT called in dry-run mode
        mock_git.create_branch.assert_not_called()
        mock_git.add.assert_not_called()
        mock_git.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_create_pr(self):
        """Test RefuelWorkflow dry-run mode does not create PR (T090b)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock runner
        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Issue 1",
                    body="Body 1",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
            ]
        )
        mock_github.create_pr = AsyncMock()

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=1, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify GitHub PR creation was NOT called
        mock_github.create_pr.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_invoke_agents(self):
        """Test RefuelWorkflow dry-run mode does not invoke agents (T090b)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.issue_fixer import IssueFixerAgent
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock runners
        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Issue 1",
                    body="Body 1",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
            ]
        )

        mock_agent = MagicMock(spec=IssueFixerAgent)
        mock_agent.execute = AsyncMock()

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            github_runner=mock_github,
            issue_fixer_agent=mock_agent,
        )

        inputs = RefuelInputs(label="tech-debt", limit=1, dry_run=True)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify agents were NOT invoked in dry-run mode
        mock_agent.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_event_sequence_matches_real_run(self):
        """Test RefuelWorkflow dry-run emits same event types as real run (T090b)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitResult, GitRunner
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Setup mocks for real run
        mock_git_real = MagicMock(spec=GitRunner)
        mock_git_real.create_branch = AsyncMock(
            return_value=GitResult(success=True, output="", error=None, duration_ms=100)
        )

        mock_github_real = MagicMock(spec=GitHubCLIRunner)
        mock_github_real.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Issue 1",
                    body="Body 1",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
            ]
        )

        # Execute real run
        workflow_real = RefuelWorkflow(
            config=RefuelConfig(),
            git_runner=mock_git_real,
            github_runner=mock_github_real,
        )
        inputs_real = RefuelInputs(label="tech-debt", limit=1, dry_run=False)

        real_events = []
        async for event in workflow_real.execute(inputs_real):
            real_events.append(event)

        # Setup mocks for dry run
        mock_git_dry = MagicMock(spec=GitRunner)
        mock_github_dry = MagicMock(spec=GitHubCLIRunner)
        mock_github_dry.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Issue 1",
                    body="Body 1",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
            ]
        )

        # Execute dry run
        workflow_dry = RefuelWorkflow(
            config=RefuelConfig(),
            git_runner=mock_git_dry,
            github_runner=mock_github_dry,
        )
        inputs_dry = RefuelInputs(label="tech-debt", limit=1, dry_run=True)

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
        assert any(isinstance(e, RefuelStarted) for e in real_events)
        assert any(isinstance(e, RefuelStarted) for e in dry_events)

        # Verify both have completed event
        assert any(isinstance(e, RefuelCompleted) for e in real_events)
        assert any(isinstance(e, RefuelCompleted) for e in dry_events)
