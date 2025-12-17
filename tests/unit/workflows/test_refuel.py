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
        assert inputs.parallel is False
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
    async def test_execute_raises_not_implemented(self):
        """Test execute() raises NotImplementedError with Spec 26 message (T013)."""
        workflow = RefuelWorkflow()
        inputs = RefuelInputs()

        with pytest.raises(NotImplementedError, match="Spec 26"):
            async for _ in workflow.execute(inputs):
                pass


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
