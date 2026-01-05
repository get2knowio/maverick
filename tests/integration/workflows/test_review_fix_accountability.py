"""Integration tests for review-fix accountability feature.

This module validates the end-to-end behavior of the review-fix accountability
workflow, testing the complete fix loop lifecycle including:
- Registry creation and filtering (T053)
- Deferred item re-queuing (T054)
- Blocked item handling (T055)
- Missing fixer output auto-defer (T056)
- Max iterations exit condition (T057)
- No actionable items exit condition (T058)
- Issue creation with attempt history (T059)
- Issue labels including tech-debt and severity (T060)
- Deleted file auto-blocking (T061)
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.library.actions.review_registry import (
    check_fix_loop_exit,
    create_issue_registry,
    create_tech_debt_issues,
    detect_deleted_files,
    prepare_fixer_input,
    update_issue_registry,
)
from maverick.models.fixer_io import (
    FixerOutput,
    FixerOutputItem,
)
from maverick.models.review_registry import (
    FindingCategory,
    FindingStatus,
    FixAttempt,
    IssueRegistry,
    ReviewFinding,
    Severity,
    TrackedFinding,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_review_findings() -> list[dict[str, Any]]:
    """Create sample ReviewFinding dictionaries for testing.

    Returns a set of findings covering various severities and categories.
    """
    return [
        {
            "id": "RS001",
            "severity": "critical",
            "category": "security",
            "title": "SQL injection vulnerability",
            "description": "User input directly concatenated into SQL query",
            "file_path": "src/db/queries.py",
            "line_start": 42,
            "line_end": 48,
            "suggested_fix": "Use parameterized queries",
            "source": "spec_reviewer",
        },
        {
            "id": "RS002",
            "severity": "major",
            "category": "correctness",
            "title": "Missing error handling",
            "description": "Function does not handle exceptions",
            "file_path": "src/api/users.py",
            "line_start": 87,
            "line_end": 92,
            "suggested_fix": "Add try-except block",
            "source": "spec_reviewer",
        },
        {
            "id": "RS003",
            "severity": "minor",
            "category": "style",
            "title": "Inconsistent naming convention",
            "description": "Variable uses camelCase instead of snake_case",
            "file_path": "src/utils/helpers.py",
            "line_start": 15,
            "line_end": 15,
            "suggested_fix": "Rename to user_name",
            "source": "spec_reviewer",
        },
    ]


@pytest.fixture
def sample_tech_findings() -> list[dict[str, Any]]:
    """Create sample technical ReviewFinding dictionaries.

    Returns findings from technical reviewer perspective.
    """
    return [
        {
            "id": "RT001",
            "severity": "critical",
            "category": "performance",
            "title": "N+1 query detected",
            "description": "Loop causes N+1 database queries",
            "file_path": "src/api/orders.py",
            "line_start": 120,
            "line_end": 135,
            "suggested_fix": "Use eager loading or batch query",
            "source": "tech_reviewer",
        },
        {
            "id": "RT002",
            "severity": "major",
            "category": "maintainability",
            "title": "Duplicate code block",
            "description": "Same logic repeated in multiple functions",
            "file_path": "src/services/payment.py",
            "line_start": 50,
            "line_end": 70,
            "suggested_fix": "Extract to shared utility function",
            "source": "tech_reviewer",
        },
    ]


@pytest.fixture
def sample_fixer_output_fixed() -> FixerOutput:
    """Create sample FixerOutput with all items fixed."""
    return FixerOutput(
        items=(
            FixerOutputItem(
                finding_id="RS001",
                status="fixed",
                justification=None,
                changes_made="Updated to parameterized queries",
            ),
            FixerOutputItem(
                finding_id="RS002",
                status="fixed",
                justification=None,
                changes_made="Added try-except block with proper logging",
            ),
        ),
        summary="Fixed 2 issues successfully",
    )


@pytest.fixture
def sample_fixer_output_partial() -> FixerOutput:
    """Create sample FixerOutput with mixed results."""
    return FixerOutput(
        items=(
            FixerOutputItem(
                finding_id="RS001",
                status="fixed",
                justification=None,
                changes_made="Applied parameterized queries",
            ),
            FixerOutputItem(
                finding_id="RS002",
                status="deferred",
                justification="Need more context from database schema",
                changes_made=None,
            ),
            FixerOutputItem(
                finding_id="RT001",
                status="blocked",
                justification="Requires database migration that is out of scope",
                changes_made=None,
            ),
        ),
        summary="Fixed 1, deferred 1, blocked 1",
    )


def create_mock_issue(
    number: int = 123,
    html_url: str = "https://github.com/owner/repo/issues/123",
) -> MagicMock:
    """Create a mock GitHub Issue object.

    Args:
        number: Issue number.
        html_url: Issue URL.

    Returns:
        Mock Issue object with number and html_url attributes.
    """
    mock_issue = MagicMock()
    mock_issue.number = number
    mock_issue.html_url = html_url
    return mock_issue


def create_mock_github_client(
    issues: list[MagicMock] | None = None,
) -> MagicMock:
    """Create a mock GitHubClient for testing.

    Args:
        issues: List of mock Issue objects to return from create_issue calls.
            If None, creates a default successful issue.

    Returns:
        Mock GitHubClient with create_issue method.
    """
    if issues is None:
        issues = [create_mock_issue()]

    mock_client = MagicMock()
    # Track call count and return issues sequentially
    issue_iter = iter(issues)

    async def mock_create_issue(**kwargs: Any) -> MagicMock:
        # Store the call arguments for assertions
        mock_client.create_issue_calls.append(kwargs)
        return next(issue_iter)

    mock_client.create_issue = AsyncMock(side_effect=mock_create_issue)
    mock_client.create_issue_calls: list[dict[str, Any]] = []

    return mock_client


# =============================================================================
# Helper Functions
# =============================================================================


def create_tracked_finding(
    finding_id: str,
    severity: Severity,
    status: FindingStatus = FindingStatus.open,
    file_path: str | None = "src/test.py",
    attempts: list[FixAttempt] | None = None,
) -> TrackedFinding:
    """Helper to create a TrackedFinding for testing.

    Args:
        finding_id: Unique identifier for the finding.
        severity: Severity level.
        status: Current status of the finding.
        file_path: Path to the affected file.
        attempts: List of fix attempts made.

    Returns:
        TrackedFinding instance.
    """
    finding = ReviewFinding(
        id=finding_id,
        severity=severity,
        category=FindingCategory.correctness,
        title=f"Finding {finding_id}",
        description=f"Description for {finding_id}",
        file_path=file_path,
        line_start=10,
        line_end=15,
        suggested_fix=None,
        source="spec_reviewer",
    )
    tracked = TrackedFinding(finding=finding, status=status)
    if attempts:
        tracked.attempts = attempts
    return tracked


def create_registry_with_findings(
    findings_spec: list[tuple[str, Severity, FindingStatus]],
    current_iteration: int = 0,
    max_iterations: int = 3,
) -> IssueRegistry:
    """Helper to create an IssueRegistry with specified findings.

    Args:
        findings_spec: List of (id, severity, status) tuples.
        current_iteration: Current iteration number.
        max_iterations: Maximum iterations allowed.

    Returns:
        IssueRegistry instance.
    """
    findings = [
        create_tracked_finding(fid, sev, status) for fid, sev, status in findings_spec
    ]
    return IssueRegistry(
        findings=findings,
        current_iteration=current_iteration,
        max_iterations=max_iterations,
    )


# =============================================================================
# Integration Test Classes
# =============================================================================


class TestRegistryActionableFiltering:
    """T053: Test registry correctly filters actionable items by severity and status."""

    @pytest.mark.asyncio
    async def test_filters_by_severity_critical_and_major_only(self) -> None:
        """Verify only critical and major severity findings are actionable.

        Actionable findings should exclude minor severity items even if
        they have open status.
        """
        spec_findings = [
            {
                "id": "RS001",
                "severity": "critical",
                "category": "security",
                "title": "Critical issue",
                "description": "Needs immediate fix",
                "file_path": "src/a.py",
                "line_start": 10,
            },
            {
                "id": "RS002",
                "severity": "major",
                "category": "correctness",
                "title": "Major issue",
                "description": "Important fix needed",
                "file_path": "src/b.py",
                "line_start": 20,
            },
            {
                "id": "RS003",
                "severity": "minor",
                "category": "style",
                "title": "Minor issue",
                "description": "Nice to fix",
                "file_path": "src/c.py",
                "line_start": 30,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,
            tech_findings=[],
            max_iterations=3,
        )

        actionable = registry.get_actionable()

        # Only critical and major should be actionable
        assert len(actionable) == 2
        ids = {tf.finding.id for tf in actionable}
        assert ids == {"RS001", "RS002"}

    @pytest.mark.asyncio
    async def test_filters_by_status_open_and_deferred_only(self) -> None:
        """Verify only open and deferred status findings are actionable.

        Fixed and blocked findings should be excluded from actionable list.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
                ("RS002", Severity.critical, FindingStatus.fixed),
                ("RS003", Severity.major, FindingStatus.blocked),
                ("RS004", Severity.major, FindingStatus.deferred),
            ]
        )

        actionable = registry.get_actionable()

        # Only open and deferred should be actionable
        assert len(actionable) == 2
        ids = {tf.finding.id for tf in actionable}
        assert ids == {"RS001", "RS004"}

    @pytest.mark.asyncio
    async def test_combined_severity_and_status_filtering(self) -> None:
        """Verify combined filtering by both severity and status.

        Only findings that are both high-severity (critical/major) AND
        have actionable status (open/deferred) should be included.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),  # Actionable
                ("RS002", Severity.minor, FindingStatus.open),  # Not actionable (minor)
                (
                    "RS003",
                    Severity.major,
                    FindingStatus.fixed,
                ),  # Not actionable (fixed)
                ("RS004", Severity.major, FindingStatus.deferred),  # Actionable
                ("RS005", Severity.critical, FindingStatus.blocked),  # Not actionable
            ]
        )

        actionable = registry.get_actionable()

        assert len(actionable) == 2
        ids = {tf.finding.id for tf in actionable}
        assert ids == {"RS001", "RS004"}


class TestDeferredItemRequeue:
    """T054: Test deferred items re-queue on next iteration."""

    @pytest.mark.asyncio
    async def test_deferred_items_appear_in_next_iteration_input(self) -> None:
        """Verify deferred items are included in fixer input for next iteration.

        After a finding is deferred, it should be re-queued for the next
        iteration's fix attempt.
        """
        # Create registry with a deferred finding
        finding = create_tracked_finding(
            "RS001", Severity.major, FindingStatus.deferred
        )
        finding.attempts.append(
            FixAttempt(
                iteration=0,
                timestamp=datetime.now(),
                outcome=FindingStatus.deferred,
                justification="Need more context",
                changes_made=None,
            )
        )
        registry = IssueRegistry(
            findings=[finding],
            current_iteration=1,
            max_iterations=3,
        )

        # Prepare fixer input for next iteration
        fixer_input = await prepare_fixer_input(registry, context="Test")

        # Deferred item should be included
        assert len(fixer_input.items) == 1
        assert fixer_input.items[0].finding_id == "RS001"
        assert fixer_input.iteration == 2
        # Previous attempt should be included
        assert len(fixer_input.items[0].previous_attempts) == 1

    @pytest.mark.asyncio
    async def test_deferred_item_preserves_attempt_history(self) -> None:
        """Verify deferred item includes full attempt history in subsequent input.

        The fixer should receive the history of all previous attempts
        to provide context for the next fix attempt.
        """
        finding = create_tracked_finding(
            "RS001", Severity.critical, FindingStatus.deferred
        )
        # Add two previous attempts
        finding.attempts.extend(
            [
                FixAttempt(
                    iteration=0,
                    timestamp=datetime(2025, 1, 1, 10, 0, 0),
                    outcome=FindingStatus.deferred,
                    justification="Missing test file",
                    changes_made=None,
                ),
                FixAttempt(
                    iteration=1,
                    timestamp=datetime(2025, 1, 1, 11, 0, 0),
                    outcome=FindingStatus.deferred,
                    justification="Still missing context",
                    changes_made=None,
                ),
            ]
        )
        registry = IssueRegistry(
            findings=[finding],
            current_iteration=2,
            max_iterations=3,
        )

        fixer_input = await prepare_fixer_input(registry)

        # Both attempts should be in history
        assert len(fixer_input.items[0].previous_attempts) == 2
        assert (
            fixer_input.items[0].previous_attempts[0]["justification"]
            == "Missing test file"
        )
        assert (
            fixer_input.items[0].previous_attempts[1]["justification"]
            == "Still missing context"
        )


class TestBlockedItemHandling:
    """T055: Test blocked items do not re-queue."""

    @pytest.mark.asyncio
    async def test_blocked_items_excluded_from_fixer_input(self) -> None:
        """Verify blocked items are not included in fixer input.

        Once a finding is blocked, it should not be sent to the fixer again.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.blocked),
                ("RS002", Severity.major, FindingStatus.open),
            ]
        )

        fixer_input = await prepare_fixer_input(registry)

        # Only open item should be included
        assert len(fixer_input.items) == 1
        assert fixer_input.items[0].finding_id == "RS002"

    @pytest.mark.asyncio
    async def test_blocked_items_marked_for_issue_creation(self) -> None:
        """Verify blocked items are included in get_for_issues().

        Blocked findings should be queued for GitHub issue creation.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.blocked),
                ("RS002", Severity.major, FindingStatus.fixed),
                ("RS003", Severity.major, FindingStatus.open),
            ]
        )

        for_issues = registry.get_for_issues()

        # Only blocked should be included (open major is still actionable)
        assert len(for_issues) == 1
        assert for_issues[0].finding.id == "RS001"


class TestMissingFixerOutputAutoDefer:
    """T056: Test missing fixer output auto-defers with justification."""

    @pytest.mark.asyncio
    async def test_auto_defers_when_fixer_omits_finding(self) -> None:
        """Verify findings not in fixer output are auto-deferred.

        If the fixer agent does not provide a status for a finding,
        it should be automatically deferred with a system justification.
        """
        # Create registry with two open findings
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
                ("RS002", Severity.major, FindingStatus.open),
            ]
        )

        # Fixer only responds to RS001
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Applied fix",
                ),
            ),
            summary="Fixed 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # RS001 should be fixed
        rs001 = next(tf for tf in updated.findings if tf.finding.id == "RS001")
        assert rs001.status == FindingStatus.fixed

        # RS002 should be auto-deferred
        rs002 = next(tf for tf in updated.findings if tf.finding.id == "RS002")
        assert rs002.status == FindingStatus.deferred
        assert len(rs002.attempts) == 1
        assert "did not provide status" in rs002.attempts[0].justification.lower()

    @pytest.mark.asyncio
    async def test_auto_defer_justification_is_meaningful(self) -> None:
        """Verify auto-defer justification provides useful context.

        The system-generated justification should clearly indicate
        that the agent did not respond with a status.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.major, FindingStatus.open),
            ]
        )

        # Empty fixer output
        fixer_output = FixerOutput(items=(), summary="No fixes")

        updated = await update_issue_registry(registry, fixer_output)

        finding = updated.findings[0]
        assert finding.status == FindingStatus.deferred
        assert "Agent did not provide status" in finding.attempts[0].justification


class TestLoopExitMaxIterations:
    """T057: Test loop exits at max iterations."""

    @pytest.mark.asyncio
    async def test_exits_when_max_iterations_reached(self) -> None:
        """Verify fix loop exits when max iterations is reached.

        Even with actionable findings remaining, the loop should exit
        at the configured maximum iterations.
        """
        # Still have actionable findings, but at max iterations
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
                ("RS002", Severity.major, FindingStatus.deferred),
            ]
        )
        registry.current_iteration = 3
        registry.max_iterations = 3

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert "Maximum iterations" in result["reason"]
        assert result["stats"]["actionable"] == 2

    @pytest.mark.asyncio
    async def test_continues_before_max_iterations(self) -> None:
        """Verify loop continues when below max iterations with actionable items."""
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
            ]
        )
        registry.current_iteration = 1
        registry.max_iterations = 3

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is False
        assert "Continue" in result["reason"]

    @pytest.mark.asyncio
    async def test_exit_reason_includes_remaining_count(self) -> None:
        """Verify exit reason includes count of remaining actionable items."""
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
                ("RS002", Severity.major, FindingStatus.deferred),
                ("RS003", Severity.major, FindingStatus.open),
            ]
        )
        registry.current_iteration = 3
        registry.max_iterations = 3

        result = await check_fix_loop_exit(registry)

        assert "3" in result["reason"]  # 3 actionable findings
        assert result["stats"]["actionable"] == 3


class TestLoopExitNoActionableItems:
    """T058: Test loop exits when no actionable items remain."""

    @pytest.mark.asyncio
    async def test_exits_when_all_fixed(self) -> None:
        """Verify loop exits when all findings are fixed.

        The loop should exit early when there are no more actionable
        findings, even before max iterations.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.fixed),
                ("RS002", Severity.major, FindingStatus.fixed),
            ]
        )
        registry.current_iteration = 1
        registry.max_iterations = 3

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert (
            "resolved" in result["reason"].lower()
            or "No actionable" in result["reason"]
        )
        assert result["stats"]["fixed"] == 2
        assert result["stats"]["actionable"] == 0

    @pytest.mark.asyncio
    async def test_exits_when_all_blocked_or_fixed(self) -> None:
        """Verify loop exits when all findings are blocked or fixed."""
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.fixed),
                ("RS002", Severity.major, FindingStatus.blocked),
            ]
        )
        registry.current_iteration = 1
        registry.max_iterations = 3

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert result["stats"]["fixed"] == 1
        assert result["stats"]["blocked"] == 1
        assert result["stats"]["actionable"] == 0

    @pytest.mark.asyncio
    async def test_exits_when_only_minor_remain(self) -> None:
        """Verify loop exits when only minor severity findings remain.

        Minor findings are not actionable, so the loop should exit.
        """
        finding = create_tracked_finding("RS001", Severity.minor, FindingStatus.open)
        registry = IssueRegistry(
            findings=[finding],
            current_iteration=0,
            max_iterations=3,
        )

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert result["stats"]["open"] == 1
        assert result["stats"]["actionable"] == 0


class TestIssueCreationWithHistory:
    """T059: Test issue creation includes full attempt history in body."""

    @pytest.mark.asyncio
    async def test_issue_body_contains_attempt_history(self) -> None:
        """Verify created issue body includes all fix attempt history.

        The GitHub issue should document all attempts made to fix
        the finding before it was deferred to a tech debt issue.
        """
        finding = create_tracked_finding(
            "RS001",
            Severity.major,
            FindingStatus.blocked,
            file_path="src/complex.py",
        )
        finding.attempts.extend(
            [
                FixAttempt(
                    iteration=0,
                    timestamp=datetime(2025, 1, 1, 10, 0, 0),
                    outcome=FindingStatus.deferred,
                    justification="Missing database context",
                    changes_made=None,
                ),
                FixAttempt(
                    iteration=1,
                    timestamp=datetime(2025, 1, 1, 11, 0, 0),
                    outcome=FindingStatus.blocked,
                    justification="Requires schema migration",
                    changes_made=None,
                ),
            ]
        )
        registry = IssueRegistry(
            findings=[finding],
            current_iteration=2,
            max_iterations=3,
        )

        # Create mock client that captures the body
        mock_client = create_mock_github_client()

        await create_tech_debt_issues(
            registry=registry,
            repo="owner/repo",
            base_labels=["tech-debt"],
            pr_number=42,
            github_client=mock_client,
        )

        # Verify body contains attempt history
        assert len(mock_client.create_issue_calls) == 1
        captured_body = mock_client.create_issue_calls[0]["body"]
        assert "Fix Attempt History" in captured_body
        assert "Iteration 0" in captured_body
        assert "Iteration 1" in captured_body
        assert "Missing database context" in captured_body
        assert "Requires schema migration" in captured_body

    @pytest.mark.asyncio
    async def test_issue_body_includes_finding_details(self) -> None:
        """Verify issue body includes finding details like file and description."""
        finding_obj = ReviewFinding(
            id="RS001",
            severity=Severity.critical,
            category=FindingCategory.security,
            title="Security vulnerability",
            description="Detailed description of the security issue",
            file_path="src/auth/login.py",
            line_start=100,
            line_end=120,
            suggested_fix="Use secure comparison",
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding_obj, status=FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[tracked], current_iteration=1, max_iterations=3
        )

        # Create mock client that captures the body
        mock_client = create_mock_github_client()

        await create_tech_debt_issues(
            registry=registry,
            repo="owner/repo",
            github_client=mock_client,
        )

        # Verify body contains finding details
        assert len(mock_client.create_issue_calls) == 1
        captured_body = mock_client.create_issue_calls[0]["body"]
        assert "src/auth/login.py" in captured_body
        assert "Detailed description of the security issue" in captured_body
        assert "Use secure comparison" in captured_body
        assert "lines 100-120" in captured_body


class TestIssueLabels:
    """T060: Test issue labels include tech-debt and severity."""

    @pytest.mark.asyncio
    async def test_includes_tech_debt_label(self) -> None:
        """Verify created issue includes 'tech-debt' label."""
        finding = create_tracked_finding("RS001", Severity.major, FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[finding], current_iteration=1, max_iterations=3
        )

        mock_client = create_mock_github_client()

        await create_tech_debt_issues(
            registry=registry,
            repo="owner/repo",
            base_labels=["tech-debt"],
            github_client=mock_client,
        )

        assert len(mock_client.create_issue_calls) == 1
        captured_labels = mock_client.create_issue_calls[0]["labels"]
        assert "tech-debt" in captured_labels

    @pytest.mark.asyncio
    async def test_includes_severity_label(self) -> None:
        """Verify created issue includes severity as a label."""
        finding = create_tracked_finding(
            "RS001", Severity.critical, FindingStatus.blocked
        )
        registry = IssueRegistry(
            findings=[finding], current_iteration=1, max_iterations=3
        )

        mock_client = create_mock_github_client()

        await create_tech_debt_issues(
            registry=registry,
            repo="owner/repo",
            base_labels=["tech-debt"],
            github_client=mock_client,
        )

        assert len(mock_client.create_issue_calls) == 1
        captured_labels = mock_client.create_issue_calls[0]["labels"]
        assert "critical" in captured_labels

    @pytest.mark.asyncio
    async def test_severity_labels_for_all_levels(self) -> None:
        """Verify all severity levels are correctly applied as labels."""
        # Test each severity level
        for severity in [Severity.critical, Severity.major, Severity.minor]:
            finding = create_tracked_finding(
                f"RS00{severity.value}", severity, FindingStatus.blocked
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=3, max_iterations=3
            )

            mock_client = create_mock_github_client()

            await create_tech_debt_issues(
                registry=registry,
                repo="owner/repo",
                github_client=mock_client,
            )

            assert len(mock_client.create_issue_calls) == 1
            captured_labels = mock_client.create_issue_calls[0]["labels"]
            assert severity.value in captured_labels, (
                f"Missing label for {severity.value}"
            )

    @pytest.mark.asyncio
    async def test_result_includes_labels(self) -> None:
        """Verify TechDebtIssueResult includes labels that were applied."""
        finding = create_tracked_finding("RS001", Severity.major, FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[finding], current_iteration=1, max_iterations=3
        )

        mock_client = create_mock_github_client()

        results = await create_tech_debt_issues(
            registry=registry,
            repo="owner/repo",
            base_labels=["tech-debt"],
            github_client=mock_client,
        )

        assert len(results) == 1
        assert "tech-debt" in results[0].labels
        assert "major" in results[0].labels


class TestDeletedFileAutoBlock:
    """T061: Test deleted file findings are auto-blocked with system justification."""

    @pytest.mark.asyncio
    async def test_auto_blocks_findings_for_deleted_files(self) -> None:
        """Verify findings referencing deleted files are auto-blocked.

        When a file referenced by a finding no longer exists, the finding
        should be automatically blocked with an appropriate justification.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directory structure but don't create the referenced file
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            # Create finding referencing non-existent file
            finding = create_tracked_finding(
                "RS001",
                Severity.critical,
                FindingStatus.open,
                file_path="src/deleted_file.py",
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            assert updated.findings[0].status == FindingStatus.blocked
            assert len(updated.findings[0].attempts) == 1
            assert "deleted" in updated.findings[0].attempts[0].justification.lower()

    @pytest.mark.asyncio
    async def test_preserves_findings_for_existing_files(self) -> None:
        """Verify findings for existing files are not blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the file that the finding references
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "existing.py").touch()

            finding = create_tracked_finding(
                "RS001",
                Severity.critical,
                FindingStatus.open,
                file_path="src/existing.py",
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # Status should remain open
            assert updated.findings[0].status == FindingStatus.open
            assert len(updated.findings[0].attempts) == 0

    @pytest.mark.asyncio
    async def test_skips_already_resolved_findings(self) -> None:
        """Verify already fixed/blocked findings are not re-processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Finding is already fixed - shouldn't be touched
            finding = create_tracked_finding(
                "RS001",
                Severity.critical,
                FindingStatus.fixed,
                file_path="src/deleted_file.py",  # File doesn't exist
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # Status should remain fixed
            assert updated.findings[0].status == FindingStatus.fixed
            assert len(updated.findings[0].attempts) == 0

    @pytest.mark.asyncio
    async def test_skips_findings_without_file_path(self) -> None:
        """Verify findings without file_path are not affected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            finding = create_tracked_finding(
                "RS001",
                Severity.critical,
                FindingStatus.open,
                file_path=None,  # No file path
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # Status should remain open
            assert updated.findings[0].status == FindingStatus.open
            assert len(updated.findings[0].attempts) == 0

    @pytest.mark.asyncio
    async def test_auto_block_justification_is_meaningful(self) -> None:
        """Verify auto-block justification provides useful context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            finding = create_tracked_finding(
                "RS001",
                Severity.major,
                FindingStatus.open,
                file_path="src/removed_module.py",
            )
            registry = IssueRegistry(
                findings=[finding], current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            assert updated.findings[0].status == FindingStatus.blocked
            justification = updated.findings[0].attempts[0].justification
            assert "Referenced file deleted" in justification

    @pytest.mark.asyncio
    async def test_handles_multiple_findings_mixed_status(self) -> None:
        """Verify correct handling of multiple findings with mixed file existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "exists.py").touch()

            findings = [
                create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.open, "src/exists.py"
                ),
                create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.open, "src/deleted1.py"
                ),
                create_tracked_finding(
                    "RS003", Severity.major, FindingStatus.fixed, "src/deleted2.py"
                ),
                create_tracked_finding(
                    "RS004", Severity.critical, FindingStatus.open, "src/deleted3.py"
                ),
            ]
            registry = IssueRegistry(
                findings=findings, current_iteration=0, max_iterations=3
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # RS001 - exists.py exists, should remain open
            assert updated.findings[0].status == FindingStatus.open
            # RS002 - deleted1.py doesn't exist, should be blocked
            assert updated.findings[1].status == FindingStatus.blocked
            # RS003 - already fixed, should remain fixed
            assert updated.findings[2].status == FindingStatus.fixed
            # RS004 - deleted3.py doesn't exist, should be blocked
            assert updated.findings[3].status == FindingStatus.blocked


class TestEndToEndFixLoop:
    """Integration tests for complete fix loop scenarios."""

    @pytest.mark.asyncio
    async def test_complete_fix_loop_all_fixed(
        self,
        sample_review_findings: list[dict[str, Any]],
        sample_tech_findings: list[dict[str, Any]],
    ) -> None:
        """Test complete fix loop where all actionable items get fixed.

        Simulates a successful fix loop where the fixer resolves
        all critical/major findings within max iterations.
        """
        # Create registry
        registry = await create_issue_registry(
            spec_findings=sample_review_findings,
            tech_findings=sample_tech_findings,
            max_iterations=3,
        )

        # First iteration: prepare input
        fixer_input = await prepare_fixer_input(registry, context="First attempt")

        # Verify only critical/major findings are included
        actionable_count = len(
            [
                f
                for f in sample_review_findings + sample_tech_findings
                if f.get("severity") in ("critical", "major")
            ]
        )
        assert len(fixer_input.items) == actionable_count

        # Simulate fixer fixing all items
        fixer_output = FixerOutput(
            items=tuple(
                FixerOutputItem(
                    finding_id=item.finding_id,
                    status="fixed",
                    justification=None,
                    changes_made=f"Fixed {item.finding_id}",
                )
                for item in fixer_input.items
            ),
            summary="All fixed",
        )

        # Update registry
        registry = await update_issue_registry(registry, fixer_output)

        # Check exit condition
        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert result["stats"]["fixed"] == actionable_count
        assert result["stats"]["actionable"] == 0

    @pytest.mark.asyncio
    async def test_fix_loop_with_deferred_and_retry(self) -> None:
        """Test fix loop where items are deferred then fixed on retry.

        Simulates a scenario where some findings are deferred on the
        first iteration but successfully fixed on a subsequent iteration.
        """
        # Create simple registry
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
                ("RS002", Severity.major, FindingStatus.open),
            ]
        )

        # First iteration: one fixed, one deferred
        fixer_input = await prepare_fixer_input(registry)
        assert len(fixer_input.items) == 2

        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed",
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="deferred",
                    justification="Need schema",
                    changes_made=None,
                ),
            ),
            summary="Partial fix",
        )

        registry = await update_issue_registry(registry, fixer_output)

        # Check - should continue
        result = await check_fix_loop_exit(registry)
        assert result["should_exit"] is False
        assert result["stats"]["deferred"] == 1

        # Second iteration: fix the deferred item
        fixer_input = await prepare_fixer_input(registry)
        assert len(fixer_input.items) == 1
        assert fixer_input.items[0].finding_id == "RS002"
        assert len(fixer_input.items[0].previous_attempts) == 1

        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Now fixed",
                ),
            ),
            summary="Fixed remaining",
        )

        registry = await update_issue_registry(registry, fixer_output)

        # Check - should exit with all fixed
        result = await check_fix_loop_exit(registry)
        assert result["should_exit"] is True
        assert result["stats"]["fixed"] == 2

    @pytest.mark.asyncio
    async def test_fix_loop_reaches_max_iterations(self) -> None:
        """Test fix loop that reaches max iterations with unresolved findings.

        Simulates a scenario where some findings cannot be fixed even
        after all allowed iterations.
        """
        registry = create_registry_with_findings(
            [
                ("RS001", Severity.critical, FindingStatus.open),
            ]
        )
        registry.max_iterations = 2

        # Iteration 1: deferred
        await prepare_fixer_input(registry)
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="Need more info",
                    changes_made=None,
                ),
            ),
            summary="Deferred",
        )
        registry = await update_issue_registry(registry, fixer_output)

        result = await check_fix_loop_exit(registry)
        assert result["should_exit"] is False

        # Iteration 2: still deferred
        await prepare_fixer_input(registry)
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="Still blocked",
                    changes_made=None,
                ),
            ),
            summary="Still deferred",
        )
        registry = await update_issue_registry(registry, fixer_output)

        # Should exit at max iterations
        result = await check_fix_loop_exit(registry)
        assert result["should_exit"] is True
        assert "Maximum iterations" in result["reason"]

        # Deferred item should be queued for issue
        for_issues = registry.get_for_issues()
        assert len(for_issues) == 1
        assert for_issues[0].finding.id == "RS001"
