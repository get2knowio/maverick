"""Unit tests for the Refuel workflow interface.

Tests the public API of the RefuelWorkflow class, including initialization,
configuration validation, data structures, and progress events.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from maverick.agents.result import AgentUsage
from maverick.config import MaverickConfig
from maverick.workflows.refuel import (
    GitHubIssue,
    IssueProcessingCompleted,
    IssueProcessingResult,
    IssueProcessingStarted,
    IssueStatus,
    RefuelCompleted,
    RefuelConfig,
    RefuelInputs,
    RefuelProgressEvent,
    RefuelResult,
    RefuelStarted,
    RefuelWorkflow,
)

# === Fixtures ===


@pytest.fixture
def sample_issue() -> GitHubIssue:
    """Create a sample GitHubIssue for testing."""
    return GitHubIssue(
        number=123,
        title="Fix bug in authentication",
        body="The login flow fails when...",
        labels=["tech-debt", "bug"],
        assignee=None,
        url="https://github.com/owner/repo/issues/123",
    )


@pytest.fixture
def sample_usage() -> AgentUsage:
    """Create a sample AgentUsage for testing."""
    return AgentUsage(
        input_tokens=1000,
        output_tokens=500,
        total_cost_usd=0.05,
        duration_ms=5000,
    )


@pytest.fixture
def sample_processing_result(
    sample_issue: GitHubIssue, sample_usage: AgentUsage
) -> IssueProcessingResult:
    """Create a sample IssueProcessingResult for testing."""
    return IssueProcessingResult(
        issue=sample_issue,
        status=IssueStatus.FIXED,
        branch="fix/issue-123",
        pr_url="https://github.com/owner/repo/pull/456",
        error=None,
        duration_ms=10000,
        agent_usage=sample_usage,
    )


# === Phase 2: GitHubIssue Tests (T003) ===


class TestGitHubIssue:
    """Tests for GitHubIssue dataclass."""

    def test_creates_with_all_fields(self, sample_issue: GitHubIssue):
        """Test GitHubIssue can be created with all fields."""
        assert sample_issue.number == 123
        assert sample_issue.title == "Fix bug in authentication"
        assert sample_issue.body == "The login flow fails when..."
        assert sample_issue.labels == ["tech-debt", "bug"]
        assert sample_issue.assignee is None
        assert sample_issue.url == "https://github.com/owner/repo/issues/123"

    def test_creates_with_none_body(self):
        """Test GitHubIssue can be created with body=None."""
        issue = GitHubIssue(
            number=1,
            title="Test",
            body=None,
            labels=[],
            assignee=None,
            url="https://github.com/owner/repo/issues/1",
        )
        assert issue.body is None

    def test_creates_with_assignee(self):
        """Test GitHubIssue can be created with an assignee."""
        issue = GitHubIssue(
            number=1,
            title="Test",
            body=None,
            labels=[],
            assignee="octocat",
            url="https://github.com/owner/repo/issues/1",
        )
        assert issue.assignee == "octocat"

    def test_immutable_frozen(self, sample_issue: GitHubIssue):
        """Test GitHubIssue is frozen (immutable) - T040."""
        with pytest.raises(FrozenInstanceError):
            sample_issue.number = 456  # type: ignore[misc]

    def test_has_slots(self):
        """Test GitHubIssue uses slots for memory efficiency."""
        assert hasattr(GitHubIssue, "__slots__")


# === Phase 2: IssueStatus Tests (T004) ===


class TestIssueStatus:
    """Tests for IssueStatus enum."""

    def test_all_status_values_exist(self):
        """Test all expected status values exist."""
        assert hasattr(IssueStatus, "PENDING")
        assert hasattr(IssueStatus, "IN_PROGRESS")
        assert hasattr(IssueStatus, "FIXED")
        assert hasattr(IssueStatus, "FAILED")
        assert hasattr(IssueStatus, "SKIPPED")

    def test_string_values(self):
        """Test IssueStatus string values and conversions - T041."""
        assert IssueStatus.PENDING.value == "pending"
        assert IssueStatus.IN_PROGRESS.value == "in_progress"
        assert IssueStatus.FIXED.value == "fixed"
        assert IssueStatus.FAILED.value == "failed"
        assert IssueStatus.SKIPPED.value == "skipped"

    def test_skipped_value_exists_for_dry_run(self):
        """Test IssueStatus.SKIPPED enum value exists for dry_run results - T029."""
        assert IssueStatus("skipped") == IssueStatus.SKIPPED

    def test_string_conversion(self):
        """Test IssueStatus can be converted to/from string."""
        # str() of an (str, Enum) returns the name, not value
        # Use .value for the string representation
        assert IssueStatus.PENDING.value == "pending"
        assert IssueStatus("fixed") == IssueStatus.FIXED


# === Phase 3: User Story 1 Tests (T010-T014) ===


class TestRefuelInputs:
    """Tests for RefuelInputs dataclass."""

    def test_default_values(self):
        """Test RefuelInputs default values - T010."""
        inputs = RefuelInputs()
        assert inputs.label == "tech-debt"
        assert inputs.limit == 5
        assert inputs.parallel is True
        assert inputs.dry_run is False
        assert inputs.auto_assign is True

    def test_immutable_frozen(self):
        """Test RefuelInputs is frozen (immutable) - T011."""
        inputs = RefuelInputs()
        with pytest.raises(FrozenInstanceError):
            inputs.label = "other"  # type: ignore[misc]

    def test_accepts_dry_run_true(self):
        """Test RefuelInputs accepts dry_run=True - T028."""
        inputs = RefuelInputs(dry_run=True)
        assert inputs.dry_run is True

    def test_accepts_parallel_true(self):
        """Test RefuelInputs accepts parallel=True - T030."""
        inputs = RefuelInputs(parallel=True)
        assert inputs.parallel is True

    def test_accepts_custom_values(self):
        """Test RefuelInputs accepts all custom values."""
        inputs = RefuelInputs(
            label="custom-label",
            limit=10,
            parallel=True,
            dry_run=True,
            auto_assign=False,
        )
        assert inputs.label == "custom-label"
        assert inputs.limit == 10
        assert inputs.parallel is True
        assert inputs.dry_run is True
        assert inputs.auto_assign is False


class TestRefuelResult:
    """Tests for RefuelResult dataclass."""

    def test_has_all_required_fields(
        self, sample_processing_result: IssueProcessingResult
    ):
        """Test RefuelResult has all required fields and success flag - T012."""
        result = RefuelResult(
            success=True,
            issues_found=5,
            issues_processed=3,
            issues_fixed=3,
            issues_failed=0,
            issues_skipped=2,
            results=[sample_processing_result],
            total_duration_ms=30000,
            total_cost_usd=0.15,
        )
        assert result.success is True
        assert result.issues_found == 5
        assert result.issues_processed == 3
        assert result.issues_fixed == 3
        assert result.issues_failed == 0
        assert result.issues_skipped == 2
        assert len(result.results) == 1
        assert result.total_duration_ms == 30000
        assert result.total_cost_usd == 0.15

    def test_total_duration_and_cost_accessible(
        self, sample_processing_result: IssueProcessingResult
    ):
        """Test RefuelResult total_duration_ms and total_cost_usd accessible (T035)."""
        result = RefuelResult(
            success=True,
            issues_found=1,
            issues_processed=1,
            issues_fixed=1,
            issues_failed=0,
            issues_skipped=0,
            results=[sample_processing_result],
            total_duration_ms=5000,
            total_cost_usd=0.05,
        )
        assert isinstance(result.total_duration_ms, int)
        assert isinstance(result.total_cost_usd, float)

    def test_issues_found_zero_represents_empty_label_match(self):
        """Test RefuelResult with issues_found=0 represents empty label match - T036."""
        result = RefuelResult(
            success=True,
            issues_found=0,
            issues_processed=0,
            issues_fixed=0,
            issues_failed=0,
            issues_skipped=0,
            results=[],
            total_duration_ms=100,
            total_cost_usd=0.0,
        )
        assert result.issues_found == 0
        assert result.results == []

    def test_success_true_when_issues_failed_zero(
        self, sample_processing_result: IssueProcessingResult
    ):
        """Test RefuelResult.success=True when issues_failed=0 - T039."""
        result = RefuelResult(
            success=True,
            issues_found=1,
            issues_processed=1,
            issues_fixed=1,
            issues_failed=0,
            issues_skipped=0,
            results=[sample_processing_result],
            total_duration_ms=5000,
            total_cost_usd=0.05,
        )
        assert result.success is True
        assert result.issues_failed == 0

    def test_immutable_frozen(self, sample_processing_result: IssueProcessingResult):
        """Test RefuelResult is frozen (immutable)."""
        result = RefuelResult(
            success=True,
            issues_found=1,
            issues_processed=1,
            issues_fixed=1,
            issues_failed=0,
            issues_skipped=0,
            results=[sample_processing_result],
            total_duration_ms=5000,
            total_cost_usd=0.05,
        )
        with pytest.raises(FrozenInstanceError):
            result.success = False  # type: ignore[misc]


class TestRefuelWorkflow:
    """Tests for RefuelWorkflow class."""

    def test_accepts_optional_config_in_constructor(self):
        """Test RefuelWorkflow accepts optional RefuelConfig - T014."""
        # With no config
        workflow1 = RefuelWorkflow()
        assert workflow1._config is not None

        # With config
        config = RefuelConfig(default_label="custom")
        workflow2 = RefuelWorkflow(config=config)
        assert workflow2._config == config

    @pytest.mark.asyncio
    async def test_execute_yields_events(self):
        """Test execute() yields progress events when executed (T013)."""
        workflow = RefuelWorkflow()
        inputs = RefuelInputs()

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # At minimum, RefuelStarted and RefuelCompleted should be emitted
        assert len(events) >= 2
        assert isinstance(events[0], RefuelStarted)
        assert isinstance(events[-1], RefuelCompleted)


# === Phase 4: User Story 2 Tests (T018-T022) ===


class TestRefuelStarted:
    """Tests for RefuelStarted progress event."""

    def test_has_inputs_and_issues_found_fields(self):
        """Test RefuelStarted has inputs and issues_found fields (T018)."""
        inputs = RefuelInputs()
        event = RefuelStarted(inputs=inputs, issues_found=5)

        assert event.inputs == inputs
        assert event.issues_found == 5
        assert isinstance(event.inputs, RefuelInputs)
        assert isinstance(event.issues_found, int)

    def test_frozen_with_slots(self):
        """Test RefuelStarted is frozen dataclass with slots - T022."""
        inputs = RefuelInputs()
        event = RefuelStarted(inputs=inputs, issues_found=5)

        with pytest.raises(FrozenInstanceError):
            event.issues_found = 10  # type: ignore[misc]

        assert hasattr(RefuelStarted, "__slots__")


class TestIssueProcessingStarted:
    """Tests for IssueProcessingStarted progress event."""

    def test_has_issue_index_total_fields(self, sample_issue: GitHubIssue):
        """Test IssueProcessingStarted has issue, index, total fields - T019."""
        event = IssueProcessingStarted(issue=sample_issue, index=1, total=5)

        assert event.issue == sample_issue
        assert event.index == 1
        assert event.total == 5
        assert isinstance(event.issue, GitHubIssue)
        assert isinstance(event.index, int)
        assert isinstance(event.total, int)

    def test_frozen_with_slots(self, sample_issue: GitHubIssue):
        """Test IssueProcessingStarted is frozen dataclass with slots - T022."""
        event = IssueProcessingStarted(issue=sample_issue, index=1, total=5)

        with pytest.raises(FrozenInstanceError):
            event.index = 2  # type: ignore[misc]

        assert hasattr(IssueProcessingStarted, "__slots__")


class TestIssueProcessingCompleted:
    """Tests for IssueProcessingCompleted progress event."""

    def test_has_result_field(self, sample_processing_result: IssueProcessingResult):
        """Test IssueProcessingCompleted has result field - T020."""
        event = IssueProcessingCompleted(result=sample_processing_result)

        assert event.result == sample_processing_result
        assert isinstance(event.result, IssueProcessingResult)

    def test_frozen_with_slots(self, sample_processing_result: IssueProcessingResult):
        """Test IssueProcessingCompleted is frozen dataclass with slots - T022."""
        event = IssueProcessingCompleted(result=sample_processing_result)

        with pytest.raises(FrozenInstanceError):
            event.result = sample_processing_result  # type: ignore[misc]

        assert hasattr(IssueProcessingCompleted, "__slots__")


class TestRefuelCompleted:
    """Tests for RefuelCompleted progress event."""

    def test_has_result_field(self, sample_processing_result: IssueProcessingResult):
        """Test RefuelCompleted has result field - T021."""
        refuel_result = RefuelResult(
            success=True,
            issues_found=1,
            issues_processed=1,
            issues_fixed=1,
            issues_failed=0,
            issues_skipped=0,
            results=[sample_processing_result],
            total_duration_ms=5000,
            total_cost_usd=0.05,
        )
        event = RefuelCompleted(result=refuel_result)

        assert event.result == refuel_result
        assert isinstance(event.result, RefuelResult)

    def test_frozen_with_slots(self, sample_processing_result: IssueProcessingResult):
        """Test RefuelCompleted is frozen dataclass with slots - T022."""
        refuel_result = RefuelResult(
            success=True,
            issues_found=1,
            issues_processed=1,
            issues_fixed=1,
            issues_failed=0,
            issues_skipped=0,
            results=[sample_processing_result],
            total_duration_ms=5000,
            total_cost_usd=0.05,
        )
        event = RefuelCompleted(result=refuel_result)

        with pytest.raises(FrozenInstanceError):
            event.result = refuel_result  # type: ignore[misc]

        assert hasattr(RefuelCompleted, "__slots__")


class TestRefuelProgressEvent:
    """Tests for RefuelProgressEvent type alias."""

    def test_type_alias_covers_all_events(self):
        """Test RefuelProgressEvent is union of all 4 event types - T027."""
        # This is a runtime type check to verify the union type
        # The actual type checking is done by mypy
        assert RefuelProgressEvent == (
            RefuelStarted
            | IssueProcessingStarted
            | IssueProcessingCompleted
            | RefuelCompleted
        )


# === Phase 5-7: User Stories 3-5 Tests (T028-T035) ===


class TestIssueProcessingResult:
    """Tests for IssueProcessingResult dataclass."""

    def test_agent_usage_field_holds_agent_usage(
        self, sample_issue: GitHubIssue, sample_usage: AgentUsage
    ):
        """Test IssueProcessingResult.agent_usage holds AgentUsage instance - T033."""
        result = IssueProcessingResult(
            issue=sample_issue,
            status=IssueStatus.FIXED,
            branch="fix/issue-123",
            pr_url="https://github.com/owner/repo/pull/456",
            error=None,
            duration_ms=5000,
            agent_usage=sample_usage,
        )
        assert isinstance(result.agent_usage, AgentUsage)
        assert result.agent_usage.input_tokens == 1000
        assert result.agent_usage.output_tokens == 500

    def test_duration_ms_field_is_int(
        self, sample_issue: GitHubIssue, sample_usage: AgentUsage
    ):
        """Test IssueProcessingResult.duration_ms field is int - T034."""
        result = IssueProcessingResult(
            issue=sample_issue,
            status=IssueStatus.FIXED,
            branch="fix/issue-123",
            pr_url="https://github.com/owner/repo/pull/456",
            error=None,
            duration_ms=5000,
            agent_usage=sample_usage,
        )
        assert isinstance(result.duration_ms, int)

    def test_skipped_with_all_optional_fields_none(
        self, sample_issue: GitHubIssue, sample_usage: AgentUsage
    ):
        """Test IssueProcessingResult with SKIPPED and optional fields None (T037)."""
        result = IssueProcessingResult(
            issue=sample_issue,
            status=IssueStatus.SKIPPED,
            branch=None,
            pr_url=None,
            error=None,
            duration_ms=100,
            agent_usage=sample_usage,
        )
        assert result.status == IssueStatus.SKIPPED
        assert result.branch is None
        assert result.pr_url is None
        assert result.error is None

    def test_failed_has_error_field(
        self, sample_issue: GitHubIssue, sample_usage: AgentUsage
    ):
        """Test IssueProcessingResult with status=FAILED has error field - T038."""
        result = IssueProcessingResult(
            issue=sample_issue,
            status=IssueStatus.FAILED,
            branch="fix/issue-123",
            pr_url=None,
            error="Agent execution failed: timeout",
            duration_ms=30000,
            agent_usage=sample_usage,
        )
        assert result.status == IssueStatus.FAILED
        assert result.error is not None
        assert "timeout" in result.error


# === Phase 6: User Story 4 - RefuelConfig Tests (T031-T032) ===


class TestRefuelConfig:
    """Tests for RefuelConfig Pydantic model."""

    def test_default_values(self):
        """Test RefuelConfig default values."""
        config = RefuelConfig()
        assert config.default_label == "tech-debt"
        assert config.branch_prefix == "fix/issue-"
        assert config.link_pr_to_issue is True
        assert config.close_on_merge is False
        assert config.skip_if_assigned is True
        assert config.max_parallel == 3

    def test_max_parallel_validates_range(self):
        """Test RefuelConfig.max_parallel validates range 1-10 - T031."""
        # Valid values
        config_min = RefuelConfig(max_parallel=1)
        assert config_min.max_parallel == 1

        config_max = RefuelConfig(max_parallel=10)
        assert config_max.max_parallel == 10

        # Invalid values
        with pytest.raises(ValidationError):
            RefuelConfig(max_parallel=0)

        with pytest.raises(ValidationError):
            RefuelConfig(max_parallel=11)

    def test_branch_prefix_validation(self):
        """Test RefuelConfig.branch_prefix validation - T032."""
        # Valid: ends with /
        config1 = RefuelConfig(branch_prefix="feature/")
        assert config1.branch_prefix == "feature/"

        # Valid: ends with -
        config2 = RefuelConfig(branch_prefix="fix-issue-")
        assert config2.branch_prefix == "fix-issue-"

        # Invalid: doesn't end with / or -
        with pytest.raises(ValidationError):
            RefuelConfig(branch_prefix="invalid")

        with pytest.raises(ValidationError):
            RefuelConfig(branch_prefix="prefix_")

    def test_frozen_config(self):
        """Test RefuelConfig is frozen (immutable)."""
        config = RefuelConfig()
        with pytest.raises(ValidationError):
            config.max_parallel = 5  # type: ignore[misc]


# === Phase 8: Polish Tests (T042-T043) ===


class TestInterfaceExports:
    """Tests for module exports and integration."""

    def test_all_types_importable_from_refuel(self):
        """Test all interface types importable from maverick.workflows.refuel - T042."""
        # This test verifies all exports work - if imports fail, the test fails
        from maverick.workflows.refuel import (
            GitHubIssue,
            IssueProcessingCompleted,
            IssueProcessingResult,
            IssueProcessingStarted,
            IssueStatus,
            RefuelCompleted,
            RefuelConfig,
            RefuelInputs,
            RefuelProgressEvent,
            RefuelResult,
            RefuelStarted,
            RefuelWorkflow,
        )

        # Verify they're the correct types
        assert GitHubIssue is not None
        assert IssueStatus is not None
        assert RefuelInputs is not None
        assert IssueProcessingResult is not None
        assert RefuelResult is not None
        assert RefuelConfig is not None
        assert RefuelStarted is not None
        assert IssueProcessingStarted is not None
        assert IssueProcessingCompleted is not None
        assert RefuelCompleted is not None
        assert RefuelProgressEvent is not None
        assert RefuelWorkflow is not None


class TestMaverickConfigIntegration:
    """Tests for MaverickConfig integration."""

    def test_maverick_config_refuel_field_exists(self):
        """Test MaverickConfig.refuel field exists and returns RefuelConfig - T043."""
        config = MaverickConfig()
        assert hasattr(config, "refuel")
        assert isinstance(config.refuel, RefuelConfig)
        assert config.refuel.default_label == "tech-debt"
        assert config.refuel.max_parallel == 3


# === User Story 2: RefuelWorkflow.execute() Implementation Tests ===


class TestRefuelWorkflowExecution:
    """Tests for RefuelWorkflow.execute() implementation."""

    @pytest.mark.asyncio
    async def test_issue_discovery_via_github_runner(self):
        """Test RefuelWorkflow discovers issues via GitHubCLIRunner.list_issues() - T037."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Create mock GitHubCLIRunner
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

        inputs = RefuelInputs(label="tech-debt", limit=5)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify list_issues was called with correct label
        mock_github.list_issues.assert_called_once()
        call_kwargs = mock_github.list_issues.call_args.kwargs
        assert call_kwargs["label"] == "tech-debt"
        assert call_kwargs["limit"] == 5

        # Verify RefuelStarted event contains correct issues_found count
        started_events = [e for e in events if isinstance(e, RefuelStarted)]
        assert len(started_events) == 1
        assert started_events[0].issues_found == 2

    @pytest.mark.asyncio
    async def test_branch_creation_per_issue(self):
        """Test RefuelWorkflow creates unique branch per issue - T038."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitResult, GitRunner
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock runners
        mock_git = MagicMock(spec=GitRunner)
        mock_git.create_branch = AsyncMock(
            return_value=GitResult(success=True, output="", error=None, duration_ms=100)
        )

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

        config = RefuelConfig(branch_prefix="fix/issue-")
        workflow = RefuelWorkflow(
            config=config,
            git_runner=mock_git,
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=1)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify branch creation called with correct branch name
        mock_git.create_branch.assert_called()
        branch_name = mock_git.create_branch.call_args[0][0]
        assert branch_name == "fix/issue-123"

    @pytest.mark.asyncio
    async def test_issue_isolation_one_failure_does_not_crash_others(self):
        """Test RefuelWorkflow isolates issues: one failure doesn't crash others - T039."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.issue_fixer import IssueFixerAgent
        from maverick.runners.git import GitResult, GitRunner
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner
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
                RunnerGitHubIssue(
                    number=2,
                    title="Issue 2",
                    body="Body 2",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/2",
                ),
                RunnerGitHubIssue(
                    number=3,
                    title="Issue 3",
                    body="Body 3",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/3",
                ),
            ]
        )

        # Mock GitRunner - first issue succeeds, second fails, third succeeds
        mock_git = MagicMock(spec=GitRunner)
        mock_git.create_branch = AsyncMock(
            side_effect=[
                GitResult(success=True, output="", error=None, duration_ms=100),
                GitResult(
                    success=False,
                    output="",
                    error="Branch already exists",
                    duration_ms=100,
                ),
                GitResult(success=True, output="", error=None, duration_ms=100),
            ]
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            git_runner=mock_git,
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=3)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify all 3 issues were attempted (IssueProcessingStarted events)
        started_events = [e for e in events if isinstance(e, IssueProcessingStarted)]
        assert len(started_events) == 3

        # Verify workflow completed (RefuelCompleted event)
        completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
        assert len(completed_events) == 1

        result = completed_events[0].result
        # At least one should have failed (issue 2), but workflow should continue
        assert result.issues_failed >= 1
        # Total processed should still be 3
        assert result.issues_found == 3

    @pytest.mark.asyncio
    async def test_result_aggregation(self):
        """Test RefuelWorkflow aggregates results correctly - T040."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner
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
                RunnerGitHubIssue(
                    number=2,
                    title="Issue 2",
                    body="Body 2",
                    labels=("tech-debt",),
                    state="open",
                    assignees=("someone",),
                    url="https://github.com/owner/repo/issues/2",
                ),
            ]
        )

        config = RefuelConfig(skip_if_assigned=True)
        workflow = RefuelWorkflow(
            config=config,
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=5)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Get final result
        completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
        assert len(completed_events) == 1

        result = completed_events[0].result

        # Verify aggregation
        assert result.issues_found == 2  # Total discovered
        assert result.issues_skipped == 1  # Issue 2 is assigned
        assert result.issues_processed == result.issues_fixed + result.issues_failed
        assert len(result.results) == 2  # One result per issue

    @pytest.mark.asyncio
    async def test_progress_events_per_issue(self):
        """Test RefuelWorkflow yields progress events per issue - T041."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner
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
                RunnerGitHubIssue(
                    number=2,
                    title="Issue 2",
                    body="Body 2",
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

        inputs = RefuelInputs(label="tech-debt", limit=2)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify event sequence
        # 1. RefuelStarted
        assert isinstance(events[0], RefuelStarted)

        # 2. For each issue: IssueProcessingStarted, IssueProcessingCompleted
        started_events = [e for e in events if isinstance(e, IssueProcessingStarted)]
        completed_events = [e for e in events if isinstance(e, IssueProcessingCompleted)]

        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Verify index and total in started events
        assert started_events[0].index == 1
        assert started_events[0].total == 2
        assert started_events[1].index == 2
        assert started_events[1].total == 2

        # 3. RefuelCompleted
        assert isinstance(events[-1], RefuelCompleted)

    @pytest.mark.asyncio
    async def test_network_failure_retry_with_exponential_backoff(self):
        """Test RefuelWorkflow retries on network failures with exponential backoff - T054c."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.exceptions import GitHubError
        from maverick.runners.github import GitHubCLIRunner

        # Mock GitHubCLIRunner - fail twice then succeed
        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            side_effect=[
                GitHubError("Network timeout"),
                GitHubError("Network timeout"),
                [],  # Success on third attempt
            ]
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=5)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify list_issues was called 3 times (2 failures + 1 success)
        assert mock_github.list_issues.call_count == 3

        # Verify workflow completed successfully (empty issue list)
        completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
        assert len(completed_events) == 1
        assert completed_events[0].result.issues_found == 0

    @pytest.mark.asyncio
    async def test_issue_skip_after_max_attempts(self):
        """Test RefuelWorkflow skips issue after 3 failed attempts - T054d."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitResult, GitRunner
        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner
        mock_github = MagicMock(spec=GitHubCLIRunner)
        mock_github.list_issues = AsyncMock(
            return_value=[
                RunnerGitHubIssue(
                    number=1,
                    title="Stubborn issue",
                    body="Keeps failing",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/1",
                ),
            ]
        )

        # Mock GitRunner - always fail branch creation
        mock_git = MagicMock(spec=GitRunner)
        mock_git.create_branch = AsyncMock(
            return_value=GitResult(
                success=False, output="", error="Cannot create branch", duration_ms=100
            )
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            git_runner=mock_git,
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=1)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify branch creation was attempted (should fail and skip)
        assert mock_git.create_branch.call_count >= 1

        # Verify final result shows failure
        completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
        assert len(completed_events) == 1

        result = completed_events[0].result
        # Issue should be marked as failed (not skipped, since we attempted it)
        assert result.issues_failed >= 1 or result.issues_skipped >= 1


class TestRefuelProgressEventEmission:
    """Tests for User Story 4: RefuelWorkflow Progress Event Emission."""

    @pytest.mark.asyncio
    async def test_refuel_started_event_with_issues_found(self):
        """Test RefuelStarted event emission with issues_found field (T070)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner with 3 issues
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
                RunnerGitHubIssue(
                    number=2,
                    title="Issue 2",
                    body="Body 2",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/2",
                ),
                RunnerGitHubIssue(
                    number=3,
                    title="Issue 3",
                    body="Body 3",
                    labels=("tech-debt",),
                    state="open",
                    assignees=(),
                    url="https://github.com/owner/repo/issues/3",
                ),
            ]
        )

        workflow = RefuelWorkflow(
            config=RefuelConfig(),
            github_runner=mock_github,
        )

        inputs = RefuelInputs(label="tech-debt", limit=5)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify RefuelStarted is first event
        assert len(events) >= 1
        assert isinstance(events[0], RefuelStarted)

        # Verify it contains the correct issues_found count
        started_event = events[0]
        assert started_event.issues_found == 3

        # Verify it contains the inputs
        assert started_event.inputs == inputs
        assert started_event.inputs.label == "tech-debt"

    @pytest.mark.asyncio
    async def test_issue_processing_started_completed_event_pairs(self):
        """Test IssueProcessingStarted/Completed event pairs for each issue (T071)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.github import GitHubCLIRunner
        from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

        # Mock GitHubCLIRunner with 3 issues
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
                RunnerGitHubIssue(
                    number=2,
                    title="Issue 2",
                    body="Body 2",
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

        inputs = RefuelInputs(label="tech-debt", limit=2)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Extract IssueProcessingStarted and IssueProcessingCompleted events
        started_events = [e for e in events if isinstance(e, IssueProcessingStarted)]
        completed_events = [e for e in events if isinstance(e, IssueProcessingCompleted)]

        # Verify we have matching pairs for 2 issues
        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Verify first IssueProcessingStarted event
        first_started = started_events[0]
        assert first_started.issue.number == 1
        assert first_started.index == 1
        assert first_started.total == 2

        # Verify second IssueProcessingStarted event
        second_started = started_events[1]
        assert second_started.issue.number == 2
        assert second_started.index == 2
        assert second_started.total == 2

        # Verify first IssueProcessingCompleted event
        first_completed = completed_events[0]
        assert first_completed.result.issue.number == 1
        assert isinstance(first_completed.result, IssueProcessingResult)

        # Verify second IssueProcessingCompleted event
        second_completed = completed_events[1]
        assert second_completed.result.issue.number == 2
        assert isinstance(second_completed.result, IssueProcessingResult)

        # Verify order: for each issue, started comes before completed
        for i in range(2):
            started_idx = next(
                idx for idx, e in enumerate(events)
                if isinstance(e, IssueProcessingStarted) and e.issue.number == i + 1
            )
            completed_idx = next(
                idx for idx, e in enumerate(events)
                if isinstance(e, IssueProcessingCompleted) and e.result.issue.number == i + 1
            )
            assert started_idx < completed_idx, f"Issue {i + 1} started must come before completed"

        # Verify event sequence: RefuelStarted -> IssueProcessing pairs -> RefuelCompleted
        assert isinstance(events[0], RefuelStarted)
        assert isinstance(events[-1], RefuelCompleted)
