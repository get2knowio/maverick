"""Unit tests for review registry actions.

Tests the review_registry.py action module including:
- create_issue_registry action with deduplication
- prepare_fixer_input action with actionable filtering
- update_issue_registry action with fixer output processing
- check_fix_loop_exit action with exit conditions
- create_tech_debt_issues action with GitHub issue creation
- detect_deleted_files action with file existence checks
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import maverick.library.actions.review_registry as review_registry_module
from maverick.models.fixer_io import FixerOutput, FixerOutputItem
from maverick.models.review_registry import (
    FindingCategory,
    FindingStatus,
    FixAttempt,
    IssueRegistry,
    ReviewFinding,
    Severity,
    TrackedFinding,
)

# Get functions from the module
_is_duplicate = review_registry_module._is_duplicate
_levenshtein_distance = review_registry_module._levenshtein_distance
_lines_overlap = review_registry_module._lines_overlap
_normalized_levenshtein = review_registry_module._normalized_levenshtein
check_fix_loop_exit = review_registry_module.check_fix_loop_exit
create_issue_registry = review_registry_module.create_issue_registry
create_tech_debt_issues = review_registry_module.create_tech_debt_issues
detect_deleted_files = review_registry_module.detect_deleted_files
prepare_fixer_input = review_registry_module.prepare_fixer_input
update_issue_registry = review_registry_module.update_issue_registry

# FR-004: Weak justification validation
INVALID_JUSTIFICATION_PATTERNS = review_registry_module.INVALID_JUSTIFICATION_PATTERNS
is_weak_justification = review_registry_module.is_weak_justification
validate_justification = review_registry_module.validate_justification
JustificationValidationResult = review_registry_module.JustificationValidationResult


def make_finding(
    finding_id: str = "RS001",
    severity: str = "major",
    category: str = "correctness",
    title: str = "Test finding",
    description: str = "Test description",
    file_path: str | None = "src/test.py",
    line_start: int | None = 10,
    line_end: int | None = 15,
    source: str = "spec_reviewer",
) -> dict[str, Any]:
    """Create a finding dict for testing."""
    return {
        "id": finding_id,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_end,
        "suggested_fix": None,
        "source": source,
    }


class TestLevenshteinDistance:
    """Tests for Levenshtein distance helper functions."""

    def test_identical_strings(self) -> None:
        """Test distance between identical strings."""
        assert _levenshtein_distance("hello", "hello") == 0

    def test_empty_strings(self) -> None:
        """Test distance with empty strings."""
        assert _levenshtein_distance("", "") == 0
        assert _levenshtein_distance("hello", "") == 5
        assert _levenshtein_distance("", "world") == 5

    def test_single_character_difference(self) -> None:
        """Test distance with single character difference."""
        assert _levenshtein_distance("cat", "bat") == 1
        assert _levenshtein_distance("cat", "cats") == 1

    def test_completely_different(self) -> None:
        """Test distance with completely different strings."""
        assert _levenshtein_distance("abc", "xyz") == 3

    def test_normalized_identical(self) -> None:
        """Test normalized distance for identical strings."""
        assert _normalized_levenshtein("hello", "hello") == 0.0

    def test_normalized_completely_different(self) -> None:
        """Test normalized distance for completely different strings."""
        assert _normalized_levenshtein("abc", "xyz") == 1.0

    def test_normalized_empty(self) -> None:
        """Test normalized distance with empty strings."""
        assert _normalized_levenshtein("", "") == 0.0


class TestLinesOverlap:
    """Tests for line range overlap detection."""

    def test_exact_overlap(self) -> None:
        """Test exact line overlap."""
        assert _lines_overlap(10, 20, 10, 20) is True

    def test_partial_overlap(self) -> None:
        """Test partial line overlap."""
        assert _lines_overlap(10, 20, 15, 25) is True

    def test_no_overlap(self) -> None:
        """Test non-overlapping ranges."""
        assert _lines_overlap(10, 20, 100, 110) is False

    def test_within_tolerance(self) -> None:
        """Test overlap within tolerance."""
        # Lines 20 and 24 are within 5-line tolerance
        assert _lines_overlap(10, 20, 24, 30, tolerance=5) is True

    def test_none_values(self) -> None:
        """Test overlap with None values (conservative match)."""
        assert _lines_overlap(None, None, 10, 20) is True
        assert _lines_overlap(10, 20, None, None) is True


class TestIsDuplicate:
    """Tests for finding deduplication logic."""

    def test_same_file_overlapping_lines_similar_title(self) -> None:
        """Test duplicate detection for same file, overlapping lines, similar title."""
        f1 = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fix the bug in parser",
            description="Desc 1",
            file_path="src/parser.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        f2 = ReviewFinding(
            id="RT001",
            severity=Severity.minor,
            category=FindingCategory.correctness,
            title="Fix the bug in parser",
            description="Desc 2",
            file_path="src/parser.py",
            line_start=12,
            line_end=18,
            suggested_fix=None,
            source="tech_reviewer",
        )
        assert _is_duplicate(f1, f2) is True

    def test_different_files(self) -> None:
        """Test non-duplicate for different files."""
        f1 = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fix the bug",
            description="Desc 1",
            file_path="src/parser.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        f2 = ReviewFinding(
            id="RT001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fix the bug",
            description="Desc 2",
            file_path="src/lexer.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="tech_reviewer",
        )
        assert _is_duplicate(f1, f2) is False

    def test_different_titles(self) -> None:
        """Test non-duplicate for different titles."""
        f1 = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fix the parser bug",
            description="Desc 1",
            file_path="src/parser.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        f2 = ReviewFinding(
            id="RT001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Add type hints to functions",
            description="Desc 2",
            file_path="src/parser.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="tech_reviewer",
        )
        assert _is_duplicate(f1, f2) is False


class TestCreateIssueRegistry:
    """Tests for create_issue_registry action."""

    @pytest.mark.asyncio
    async def test_creates_registry_from_findings(self) -> None:
        """Test creates registry from reviewer findings."""
        spec_findings = [
            make_finding(
                finding_id="RS001",
                title="Spec issue 1",
                file_path="src/parser.py",
                line_start=10,
                line_end=15,
            ),
            make_finding(
                finding_id="RS002",
                title="Spec issue 2",
                file_path="src/lexer.py",
                line_start=20,
                line_end=25,
            ),
        ]
        tech_findings = [
            make_finding(
                finding_id="RT001",
                title="Tech issue 1",
                file_path="src/validator.py",
                line_start=30,
                line_end=35,
                source="tech_reviewer",
            ),
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,
            tech_findings=tech_findings,
            max_iterations=3,
        )

        assert len(registry.findings) == 3
        assert registry.current_iteration == 0
        assert registry.max_iterations == 3

    @pytest.mark.asyncio
    async def test_deduplicates_similar_findings(self) -> None:
        """Test deduplicates findings with same file/line/title."""
        spec_findings = [
            make_finding(
                finding_id="RS001",
                title="Fix the bug",
                file_path="src/test.py",
                line_start=10,
                line_end=15,
                severity="major",
            ),
        ]
        tech_findings = [
            make_finding(
                finding_id="RT001",
                title="Fix the bug",
                file_path="src/test.py",
                line_start=12,
                line_end=18,
                severity="minor",
                source="tech_reviewer",
            ),
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,
            tech_findings=tech_findings,
        )

        # Should deduplicate to 1 finding, keeping higher severity (major)
        assert len(registry.findings) == 1
        assert registry.findings[0].finding.severity == Severity.major

    @pytest.mark.asyncio
    async def test_handles_empty_findings(self) -> None:
        """Test handles empty findings list."""
        registry = await create_issue_registry(
            spec_findings=[],
            tech_findings=[],
        )

        assert len(registry.findings) == 0
        assert registry.current_iteration == 0

    @pytest.mark.asyncio
    async def test_invalid_severity_falls_back_to_minor(self) -> None:
        """Test invalid severity values fall back to minor."""
        findings = [
            {
                "id": "RS001",
                "severity": "INVALID_SEVERITY",
                "category": "correctness",
                "title": "Test issue",
                "description": "Test desc",
                "file_path": "test.py",
                "line_start": 1,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=findings,
            tech_findings=[],
        )

        assert len(registry.findings) == 1
        assert registry.findings[0].finding.severity == Severity.minor

    @pytest.mark.asyncio
    async def test_invalid_category_falls_back_to_correctness(self) -> None:
        """Test invalid category values fall back to correctness."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "INVALID_CATEGORY",
                "title": "Test issue",
                "description": "Test desc",
                "file_path": "test.py",
                "line_start": 1,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=findings,
            tech_findings=[],
        )

        assert len(registry.findings) == 1
        assert registry.findings[0].finding.category == FindingCategory.correctness


class TestPrepareFixerInput:
    """Tests for prepare_fixer_input action."""

    @pytest.mark.asyncio
    async def test_prepares_actionable_findings(self) -> None:
        """Test prepares input for actionable findings only."""
        finding1 = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Major issue",
            description="Needs fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        finding2 = ReviewFinding(
            id="RS002",
            severity=Severity.minor,
            category=FindingCategory.style,
            title="Minor issue",
            description="Low priority",
            file_path="src/test.py",
            line_start=20,
            line_end=25,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[
                TrackedFinding(finding=finding1),
                TrackedFinding(finding=finding2),
            ],
            current_iteration=0,
            max_iterations=3,
        )

        fixer_input = await prepare_fixer_input(registry, context="Test context")

        # Only major/critical findings are actionable
        assert len(fixer_input.items) == 1
        assert fixer_input.items[0].finding_id == "RS001"
        assert fixer_input.iteration == 1
        assert fixer_input.context == "Test context"

    @pytest.mark.asyncio
    async def test_includes_previous_attempts(self) -> None:
        """Test includes previous attempt history."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.deferred)
        tracked.attempts.append(
            FixAttempt(
                iteration=0,
                timestamp=datetime.now(),
                outcome=FindingStatus.deferred,
                justification="Needs more info",
                changes_made=None,
            )
        )
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=1,
            max_iterations=3,
        )

        fixer_input = await prepare_fixer_input(registry)

        assert len(fixer_input.items) == 1
        assert len(fixer_input.items[0].previous_attempts) == 1
        assert fixer_input.items[0].previous_attempts[0]["outcome"] == "deferred"


class TestUpdateIssueRegistry:
    """Tests for update_issue_registry action."""

    @pytest.mark.asyncio
    async def test_updates_findings_with_fixer_output(self) -> None:
        """Test updates findings based on fixer output."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
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

        assert updated.findings[0].status == FindingStatus.fixed
        assert len(updated.findings[0].attempts) == 1
        assert updated.current_iteration == 1

    @pytest.mark.asyncio
    async def test_auto_defers_missing_findings(self) -> None:
        """Test auto-defers findings not in fixer output."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(items=(), summary="No fixes")

        updated = await update_issue_registry(registry, fixer_output)

        assert updated.findings[0].status == FindingStatus.deferred
        assert "did not provide status" in updated.findings[0].attempts[0].justification


class TestCheckFixLoopExit:
    """Tests for check_fix_loop_exit action."""

    @pytest.mark.asyncio
    async def test_should_exit_when_max_iterations_reached(self) -> None:
        """Test should exit when max iterations reached."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=3,
            max_iterations=3,
        )

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert "Maximum iterations" in result["reason"]
        assert result["stats"]["open"] == 1

    @pytest.mark.asyncio
    async def test_should_exit_when_no_actionable(self) -> None:
        """Test should exit when no actionable findings."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.fixed)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=1,
            max_iterations=3,
        )

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is True
        assert result["stats"]["fixed"] == 1
        assert result["stats"]["actionable"] == 0

    @pytest.mark.asyncio
    async def test_should_continue_with_actionable(self) -> None:
        """Test should continue when actionable findings remain."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=1,
            max_iterations=3,
        )

        result = await check_fix_loop_exit(registry)

        assert result["should_exit"] is False
        assert result["stats"]["actionable"] == 1


class TestCreateTechDebtIssues:
    """Tests for create_tech_debt_issues action."""

    @pytest.mark.asyncio
    async def test_creates_issues_for_blocked_findings(self) -> None:
        """Test creates GitHub issues for blocked findings."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Blocked issue",
            description="Cannot be fixed",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=3,
            max_iterations=3,
        )

        # Create mock Issue object
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.html_url = "https://github.com/org/repo/issues/123"

        # Create mock GitHubClient
        mock_client = MagicMock()
        mock_client.create_issue = AsyncMock(return_value=mock_issue)

        results = await create_tech_debt_issues(
            registry=registry,
            repo="org/repo",
            base_labels=["tech-debt"],
            pr_number=42,
            github_client=mock_client,
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].issue_number == 123
        assert results[0].finding_id == "RS001"

        # Verify create_issue was called with correct arguments
        mock_client.create_issue.assert_called_once()
        call_kwargs = mock_client.create_issue.call_args.kwargs
        assert call_kwargs["repo_name"] == "org/repo"
        assert "[MAJOR] Blocked issue" in call_kwargs["title"]
        assert "tech-debt" in call_kwargs["labels"]
        assert "major" in call_kwargs["labels"]

    @pytest.mark.asyncio
    async def test_issue_title_format_by_severity(self) -> None:
        """Test GitHub issue title includes severity in correct format."""
        # Test critical severity
        finding_critical = ReviewFinding(
            id="RS001",
            severity=Severity.critical,
            category=FindingCategory.correctness,
            title="Critical issue",
            description="Very serious",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked_critical = TrackedFinding(
            finding=finding_critical, status=FindingStatus.blocked
        )
        registry_critical = IssueRegistry(
            findings=[tracked_critical],
            current_iteration=3,
            max_iterations=3,
        )

        # Test minor severity
        finding_minor = ReviewFinding(
            id="RS002",
            severity=Severity.minor,
            category=FindingCategory.style,
            title="Minor issue",
            description="Low priority",
            file_path="src/test.py",
            line_start=20,
            line_end=25,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked_minor = TrackedFinding(
            finding=finding_minor, status=FindingStatus.deferred
        )
        registry_minor = IssueRegistry(
            findings=[tracked_minor],
            current_iteration=3,
            max_iterations=3,
        )

        # Create mock GitHubClient
        mock_client = MagicMock()
        mock_issue_critical = MagicMock()
        mock_issue_critical.number = 123
        mock_issue_critical.html_url = "https://github.com/org/repo/issues/123"
        mock_issue_minor = MagicMock()
        mock_issue_minor.number = 124
        mock_issue_minor.html_url = "https://github.com/org/repo/issues/124"
        mock_client.create_issue = AsyncMock(
            side_effect=[mock_issue_critical, mock_issue_minor]
        )

        # Test critical
        results_critical = await create_tech_debt_issues(
            registry=registry_critical,
            repo="org/repo",
            github_client=mock_client,
        )
        assert "[CRITICAL]" in results_critical[0].title

        # Reset mock for minor test
        mock_client.reset_mock()
        mock_client.create_issue = AsyncMock(return_value=mock_issue_minor)

        # Test minor
        results_minor = await create_tech_debt_issues(
            registry=registry_minor,
            repo="org/repo",
            github_client=mock_client,
        )
        assert "[MINOR]" in results_minor[0].title

    @pytest.mark.asyncio
    async def test_handles_github_api_failure(self) -> None:
        """Test handles GitHub API failure gracefully."""
        from maverick.exceptions import GitHubError

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=3,
            max_iterations=3,
        )

        # Create mock GitHubClient that raises GitHubError
        mock_client = MagicMock()
        mock_client.create_issue = AsyncMock(
            side_effect=GitHubError("Authentication required")
        )

        results = await create_tech_debt_issues(
            registry=registry,
            repo="org/repo",
            github_client=mock_client,
        )

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error is not None
        # The error may be wrapped in a RetryError after exhausting retries,
        # or it may be the raw GitHubError message
        assert "GitHubError" in results[0].error or "RetryError" in results[0].error


class TestDetectDeletedFiles:
    """Tests for detect_deleted_files action."""

    @pytest.mark.asyncio
    async def test_blocks_findings_for_deleted_files(self) -> None:
        """Test blocks findings referencing deleted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file that will exist
            existing_file = Path(tmpdir) / "src" / "exists.py"
            existing_file.parent.mkdir(parents=True)
            existing_file.touch()

            # Finding for existing file
            finding1 = ReviewFinding(
                id="RS001",
                severity=Severity.major,
                category=FindingCategory.correctness,
                title="Issue in existing file",
                description="Desc",
                file_path="src/exists.py",
                line_start=10,
                line_end=15,
                suggested_fix=None,
                source="spec_reviewer",
            )
            # Finding for deleted file
            finding2 = ReviewFinding(
                id="RS002",
                severity=Severity.major,
                category=FindingCategory.correctness,
                title="Issue in deleted file",
                description="Desc",
                file_path="src/deleted.py",
                line_start=10,
                line_end=15,
                suggested_fix=None,
                source="spec_reviewer",
            )
            registry = IssueRegistry(
                findings=[
                    TrackedFinding(finding=finding1),
                    TrackedFinding(finding=finding2),
                ],
                current_iteration=0,
                max_iterations=3,
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # First finding should remain open
            assert updated.findings[0].status == FindingStatus.open
            # Second finding should be blocked
            assert updated.findings[1].status == FindingStatus.blocked
            assert "deleted" in updated.findings[1].attempts[0].justification.lower()

    @pytest.mark.asyncio
    async def test_skips_findings_without_file_path(self) -> None:
        """Test skips findings without file_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            finding = ReviewFinding(
                id="RS001",
                severity=Severity.major,
                category=FindingCategory.correctness,
                title="General issue",
                description="Desc",
                file_path=None,
                line_start=None,
                line_end=None,
                suggested_fix=None,
                source="spec_reviewer",
            )
            registry = IssueRegistry(
                findings=[TrackedFinding(finding=finding)],
                current_iteration=0,
                max_iterations=3,
            )

            updated = await detect_deleted_files(registry, tmpdir)

            # Should remain open (no file_path to check)
            assert updated.findings[0].status == FindingStatus.open
            assert len(updated.findings[0].attempts) == 0


# =============================================================================
# FR-004: Weak Justification Validation Tests
# =============================================================================


class TestIsWeakJustification:
    """Tests for is_weak_justification helper function."""

    def test_none_justification_not_weak(self) -> None:
        """Test None justification is not flagged as weak."""
        assert is_weak_justification(None) is False

    def test_empty_justification_not_weak(self) -> None:
        """Test empty justification is not flagged as weak."""
        assert is_weak_justification("") is False

    def test_out_of_scope_is_weak(self) -> None:
        """Test 'out of scope' is flagged as weak."""
        assert is_weak_justification("This is out of scope for this PR") is True

    def test_pre_existing_issue_is_weak(self) -> None:
        """Test 'pre-existing issue' is flagged as weak."""
        assert is_weak_justification("This is a pre-existing issue") is True

    def test_too_complex_is_weak(self) -> None:
        """Test 'too complex' is flagged as weak."""
        assert is_weak_justification("This is too complex to fix now") is True

    def test_would_take_too_long_is_weak(self) -> None:
        """Test 'would take too long' is flagged as weak."""
        assert is_weak_justification("This would take too long") is True

    def test_separate_pr_is_weak(self) -> None:
        """Test 'should be done in a separate PR' is flagged as weak."""
        assert is_weak_justification("This should be done in a separate PR") is True

    def test_requires_significant_refactoring_is_weak(self) -> None:
        """Test 'requires significant refactoring' is flagged as weak."""
        assert (
            is_weak_justification("This requires significant refactoring to fix")
            is True
        )

    def test_case_insensitive_matching(self) -> None:
        """Test matching is case-insensitive."""
        assert is_weak_justification("THIS IS OUT OF SCOPE") is True
        assert is_weak_justification("Out Of Scope") is True

    def test_valid_technical_justification(self) -> None:
        """Test valid technical justifications are not flagged."""
        assert (
            is_weak_justification("Requires AWS credentials not in codebase") is False
        )
        assert (
            is_weak_justification("Referenced file no longer exists in repo") is False
        )
        assert (
            is_weak_justification("API contract change needs product decision") is False
        )

    def test_unrelated_to_changes_is_weak(self) -> None:
        """Test 'unrelated to the current changes' is flagged as weak."""
        assert is_weak_justification("This is unrelated to the current changes") is True


class TestValidateJustification:
    """Tests for validate_justification function."""

    def test_fixed_status_always_valid(self) -> None:
        """Test fixed status always passes validation."""
        result = validate_justification("fixed", None)
        assert result.is_valid is True
        assert result.is_weak is False
        assert result.should_requeue is False

    def test_deferred_with_weak_excuse_rejected(self) -> None:
        """Test deferred with weak excuse is rejected and re-queued."""
        result = validate_justification("deferred", "This is a pre-existing issue")
        assert result.is_valid is False
        assert result.is_weak is True
        assert result.should_requeue is True
        assert "rejected" in result.message.lower()

    def test_deferred_with_valid_justification_accepted(self) -> None:
        """Test deferred with valid justification is accepted."""
        result = validate_justification(
            "deferred", "Need clarification from product team on expected behavior"
        )
        assert result.is_valid is True
        assert result.is_weak is False
        assert result.should_requeue is False

    def test_blocked_with_weak_excuse_flagged_but_kept(self) -> None:
        """Test blocked with weak excuse is flagged but kept blocked."""
        result = validate_justification("blocked", "This would take too long")
        assert result.is_valid is True  # Still valid, just flagged
        assert result.is_weak is True
        assert result.should_requeue is False  # Stay blocked
        assert "warning" in result.message.lower()

    def test_blocked_with_valid_justification_accepted(self) -> None:
        """Test blocked with valid technical justification is accepted."""
        result = validate_justification(
            "blocked", "Requires external credentials not available in codebase"
        )
        assert result.is_valid is True
        assert result.is_weak is False
        assert result.should_requeue is False

    def test_unknown_status_passes_through(self) -> None:
        """Test unknown status passes through."""
        result = validate_justification("unknown_status", "Some justification")
        assert result.is_valid is True
        assert result.should_requeue is False


class TestUpdateIssueRegistryWithValidation:
    """Tests for update_issue_registry with FR-004 validation."""

    @pytest.mark.asyncio
    async def test_deferred_weak_excuse_requeues_finding(self) -> None:
        """Test deferred with weak excuse re-queues the finding."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="This is a pre-existing issue",
                    changes_made=None,
                ),
            ),
            summary="Deferred 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # Finding should be re-queued as open
        assert updated.findings[0].status == FindingStatus.open
        # Attempt should be recorded with rejection note
        assert len(updated.findings[0].attempts) == 1
        assert "[REJECTED" in updated.findings[0].attempts[0].justification

    @pytest.mark.asyncio
    async def test_blocked_weak_excuse_kept_but_flagged(self) -> None:
        """Test blocked with weak excuse is kept but flagged."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="blocked",
                    justification="This would take too long",
                    changes_made=None,
                ),
            ),
            summary="Blocked 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # Finding should remain blocked
        assert updated.findings[0].status == FindingStatus.blocked
        # Justification should be flagged
        assert len(updated.findings[0].attempts) == 1
        assert "[FLAGGED" in updated.findings[0].attempts[0].justification

    @pytest.mark.asyncio
    async def test_valid_deferred_accepted(self) -> None:
        """Test valid deferred justification is accepted normally."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="Waiting for API spec clarification from team lead",
                    changes_made=None,
                ),
            ),
            summary="Deferred 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # Finding should be deferred (not re-queued)
        assert updated.findings[0].status == FindingStatus.deferred
        # Justification should not be modified
        assert len(updated.findings[0].attempts) == 1
        assert "[REJECTED" not in updated.findings[0].attempts[0].justification
        assert "[FLAGGED" not in updated.findings[0].attempts[0].justification

    @pytest.mark.asyncio
    async def test_valid_blocked_accepted(self) -> None:
        """Test valid blocked justification is accepted normally."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="blocked",
                    justification="Requires AWS credentials not available",
                    changes_made=None,
                ),
            ),
            summary="Blocked 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # Finding should be blocked
        assert updated.findings[0].status == FindingStatus.blocked
        # Justification should not be modified
        assert len(updated.findings[0].attempts) == 1
        assert "[FLAGGED" not in updated.findings[0].attempts[0].justification

    @pytest.mark.asyncio
    async def test_requeued_finding_sent_again_next_iteration(self) -> None:
        """Test re-queued finding is actionable for next iteration."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Desc",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="This is out of scope",
                    changes_made=None,
                ),
            ),
            summary="Deferred 1 issue",
        )

        updated = await update_issue_registry(registry, fixer_output)

        # Finding should be actionable (status is open)
        actionable = updated.get_actionable()
        assert len(actionable) == 1
        assert actionable[0].finding.id == "RS001"


# =============================================================================
# run_accountability_fix_loop Tests
# =============================================================================


class TestRunAccountabilityFixLoop:
    """Tests for run_accountability_fix_loop action."""

    @pytest.mark.asyncio
    async def test_exits_immediately_when_no_actionable_findings(self) -> None:
        """Test exits immediately when no actionable findings (minor severity)."""

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.minor,  # Minor is not actionable
            category=FindingCategory.style,
            title="Style issue",
            description="Minor style improvement",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )

        result = await run_accountability_fix_loop(
            registry=registry,
            max_iterations=3,
        )

        assert result["iterations_run"] == 0
        # should_continue returns False when no actionable items
        # exit_reason is "Not started" in this case since the while loop
        # never enters (minor findings aren't actionable)
        assert result["exit_reason"] == "Not started"

    @pytest.mark.asyncio
    async def test_runs_fixer_agent_and_updates_registry(self) -> None:
        """Test runs fixer agent and updates registry with results."""
        from unittest.mock import patch

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue to fix",
            description="Needs fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )

        # Mock the ReviewFixerAgent
        mock_fixer_output = FixerOutput(
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

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value=mock_fixer_output)
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry,
                max_iterations=3,
            )

        assert result["iterations_run"] == 1
        assert result["stats"]["fixed"] == 1
        # Verify agent was called
        mock_agent.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_iterates_until_all_fixed(self) -> None:
        """Test iterates until all findings are fixed."""
        from unittest.mock import patch

        from maverick.models.fixer_io import FixerInput

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding1 = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue 1",
            description="Needs fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        finding2 = ReviewFinding(
            id="RS002",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue 2",
            description="Also needs fix",
            file_path="src/test.py",
            line_start=20,
            line_end=25,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[
                TrackedFinding(finding=finding1),
                TrackedFinding(finding=finding2),
            ],
            current_iteration=0,
            max_iterations=3,
        )

        # First iteration: fix RS002, valid defer RS001
        # Second iteration: fix RS001
        call_count = 0

        async def mock_execute(fixer_input: FixerInput) -> FixerOutput:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FixerOutput(
                    items=(
                        FixerOutputItem(
                            finding_id="RS001",
                            status="deferred",
                            # Use a valid justification (not weak excuse)
                            justification="Waiting for API spec clarification",
                            changes_made=None,
                        ),
                        FixerOutputItem(
                            finding_id="RS002",
                            status="fixed",
                            justification=None,
                            changes_made="Fixed",
                        ),
                    ),
                    summary="Partial fix",
                )
            else:
                return FixerOutput(
                    items=(
                        FixerOutputItem(
                            finding_id="RS001",
                            status="fixed",
                            justification=None,
                            changes_made="Fixed",
                        ),
                    ),
                    summary="Fixed",
                )

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = mock_execute
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry,
                max_iterations=3,
            )

        assert result["iterations_run"] == 2
        assert result["stats"]["fixed"] == 2

    @pytest.mark.asyncio
    async def test_stops_at_max_iterations(self) -> None:
        """Test stops when max iterations reached."""
        from unittest.mock import patch

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Stubborn issue",
            description="Never gets fixed",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=2,
        )

        # Always defer with a valid justification
        mock_fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification="Waiting for product team decision on API",
                    changes_made=None,
                ),
            ),
            summary="Deferred",
        )

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value=mock_fixer_output)
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry,
                max_iterations=2,
            )

        assert result["iterations_run"] == 2
        assert "Maximum iterations" in result["exit_reason"]
        assert result["stats"]["deferred"] == 1

    @pytest.mark.asyncio
    async def test_accepts_dict_registry(self) -> None:
        """Test accepts registry as dict (from DSL serialization)."""
        from unittest.mock import patch

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Needs fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )
        registry_dict = registry.to_dict()

        mock_fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed",
                ),
            ),
            summary="Fixed",
        )

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value=mock_fixer_output)
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry_dict,
                max_iterations=3,
            )

        assert result["iterations_run"] == 1
        assert isinstance(result["registry"], dict)

    @pytest.mark.asyncio
    async def test_returns_registry_as_dict(self) -> None:
        """Test returns registry as dict for DSL compatibility."""
        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.minor,  # Not actionable
            category=FindingCategory.style,
            title="Style issue",
            description="Minor",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )

        result = await run_accountability_fix_loop(
            registry=registry,
            max_iterations=3,
        )

        assert isinstance(result["registry"], dict)
        assert "findings" in result["registry"]
        assert "current_iteration" in result["registry"]

    @pytest.mark.asyncio
    async def test_handles_blocked_findings(self) -> None:
        """Test handles blocked findings correctly."""
        from unittest.mock import patch

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Cannot fix",
            description="Needs external dependency",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=3,
        )

        # Return blocked with valid technical justification
        mock_fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="blocked",
                    justification="Requires AWS credentials not available",
                    changes_made=None,
                ),
            ),
            summary="Blocked",
        )

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value=mock_fixer_output)
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry,
                max_iterations=3,
            )

        # Should exit after 1 iteration (blocked is not actionable)
        assert result["iterations_run"] == 1
        assert result["stats"]["blocked"] == 1

    @pytest.mark.asyncio
    async def test_handles_fixer_returning_dict(self) -> None:
        """Test handles fixer returning dict instead of FixerOutput gracefully."""
        from unittest.mock import patch

        run_accountability_fix_loop = review_registry_module.run_accountability_fix_loop

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="Needs fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=0,
            max_iterations=2,
        )

        # First call returns dict (unexpected), second returns proper FixerOutput
        call_count = 0

        async def mock_execute_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return dict - should trigger warning and continue
                return {"items": [], "summary": "Dict response"}
            else:
                return FixerOutput(
                    items=(
                        FixerOutputItem(
                            finding_id="RS001",
                            status="fixed",
                            justification=None,
                            changes_made="Fixed",
                        ),
                    ),
                    summary="Fixed",
                )

        with patch(
            "maverick.agents.reviewers.review_fixer.ReviewFixerAgent"
        ) as MockAgent:
            mock_agent = MagicMock()
            mock_agent.execute = mock_execute_side_effect
            MockAgent.return_value = mock_agent

            result = await run_accountability_fix_loop(
                registry=registry,
                max_iterations=2,
            )

        # Should have iterated twice: first with dict (skipped), second fixed
        assert result["iterations_run"] == 2
        assert result["stats"]["fixed"] == 1


# =============================================================================
# generate_registry_summary Tests
# =============================================================================


class TestGenerateRegistrySummary:
    """Tests for generate_registry_summary action."""

    @pytest.mark.asyncio
    async def test_generates_summary_with_all_fixed(self) -> None:
        """Test generates summary when all findings are fixed."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fixed issue",
            description="Was fixed",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.fixed)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=1,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry)

        assert "All findings resolved" in result["summary"]
        assert result["stats"]["total"] == 1
        assert result["stats"]["fixed"] == 1
        assert result["stats"]["actionable_remaining"] == 0

    @pytest.mark.asyncio
    async def test_generates_summary_with_mixed_statuses(self) -> None:
        """Test generates summary with mixed statuses."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        findings = [
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS001",
                    severity=Severity.major,
                    category=FindingCategory.correctness,
                    title="Fixed",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
                status=FindingStatus.fixed,
            ),
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS002",
                    severity=Severity.major,
                    category=FindingCategory.correctness,
                    title="Blocked",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
                status=FindingStatus.blocked,
            ),
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS003",
                    severity=Severity.minor,
                    category=FindingCategory.style,
                    title="Open minor",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
                status=FindingStatus.open,
            ),
        ]
        registry = IssueRegistry(
            findings=findings,
            current_iteration=2,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry)

        assert result["stats"]["total"] == 3
        assert result["stats"]["fixed"] == 1
        assert result["stats"]["blocked"] == 1
        assert result["stats"]["open"] == 1
        assert result["stats"]["severity"]["major"] == 2
        assert result["stats"]["severity"]["minor"] == 1

    @pytest.mark.asyncio
    async def test_includes_max_iterations_warning(self) -> None:
        """Test includes warning when max iterations reached."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Deferred",
            description="Still open",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.deferred)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=3,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry, max_iterations=3)

        assert "Max iterations reached" in result["summary"]
        assert result["stats"]["max_iterations_reached"] is True

    @pytest.mark.asyncio
    async def test_includes_github_issues_count(self) -> None:
        """Test includes GitHub issues created count."""
        from maverick.library.actions.types import TechDebtIssueResult

        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Fixed",
            description="",
            file_path=None,
            line_start=None,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding, status=FindingStatus.fixed)],
            current_iteration=1,
            max_iterations=3,
        )

        issues_created = [
            TechDebtIssueResult(
                success=True,
                issue_number=123,
                issue_url="https://github.com/org/repo/issues/123",
                title="Tech debt issue",
                labels=("tech-debt",),
                finding_id="RS002",
                error=None,
            ),
            TechDebtIssueResult(
                success=False,
                issue_number=None,
                issue_url=None,
                title="Failed issue",
                labels=("tech-debt",),
                finding_id="RS003",
                error="API error",
            ),
        ]

        result = await generate_registry_summary(
            registry, issues_created=issues_created
        )

        assert "GitHub Issues Created" in result["summary"]
        assert result["stats"]["issues_created"] == 1  # Only successful ones

    @pytest.mark.asyncio
    async def test_accepts_dict_registry(self) -> None:
        """Test accepts registry as dict (from DSL serialization)."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="",
            file_path=None,
            line_start=None,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding, status=FindingStatus.fixed)],
            current_iteration=1,
            max_iterations=3,
        )
        registry_dict = registry.to_dict()

        result = await generate_registry_summary(registry_dict)

        assert result["stats"]["total"] == 1

    @pytest.mark.asyncio
    async def test_accepts_dict_issues_created(self) -> None:
        """Test accepts issues_created as list of dicts."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="",
            file_path=None,
            line_start=None,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding, status=FindingStatus.fixed)],
            current_iteration=1,
            max_iterations=3,
        )

        issues_created = [
            {"success": True, "issue_number": 123},
            {"success": False, "error": "Failed"},
        ]

        result = await generate_registry_summary(
            registry, issues_created=issues_created
        )

        assert result["stats"]["issues_created"] == 1

    @pytest.mark.asyncio
    async def test_shows_severity_breakdown(self) -> None:
        """Test shows breakdown by severity."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        findings = [
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS001",
                    severity=Severity.critical,
                    category=FindingCategory.security,
                    title="Critical",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
            ),
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS002",
                    severity=Severity.major,
                    category=FindingCategory.correctness,
                    title="Major",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
            ),
            TrackedFinding(
                finding=ReviewFinding(
                    id="RS003",
                    severity=Severity.minor,
                    category=FindingCategory.style,
                    title="Minor",
                    description="",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    suggested_fix=None,
                    source="spec_reviewer",
                ),
            ),
        ]
        registry = IssueRegistry(findings=findings)

        result = await generate_registry_summary(registry)

        assert "By Severity" in result["summary"]
        assert "Critical: 1" in result["summary"]
        assert "Major: 1" in result["summary"]
        assert "Minor: 1" in result["summary"]
        assert result["stats"]["severity"]["critical"] == 1
        assert result["stats"]["severity"]["major"] == 1
        assert result["stats"]["severity"]["minor"] == 1

    @pytest.mark.asyncio
    async def test_recommendation_for_actionable_remaining(self) -> None:
        """Test recommendation when actionable findings remain."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Open issue",
            description="Still open",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=1,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry)

        assert "actionable finding(s) remain" in result["summary"]
        assert result["stats"]["actionable_remaining"] == 1

    @pytest.mark.asyncio
    async def test_recommendation_no_actionable_with_blocked(self) -> None:
        """Test recommendation when no actionable but some blocked/deferred."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Blocked issue",
            description="Cannot fix",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding, status=FindingStatus.blocked)
        registry = IssueRegistry(
            findings=[tracked],
            current_iteration=1,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry)

        assert "No actionable findings remaining" in result["summary"]
        assert "blocked/deferred" in result["summary"]

    @pytest.mark.asyncio
    async def test_shows_iterations_run(self) -> None:
        """Test shows number of iterations run."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Issue",
            description="",
            file_path=None,
            line_start=None,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding, status=FindingStatus.fixed)],
            current_iteration=2,
            max_iterations=5,
        )

        result = await generate_registry_summary(registry, max_iterations=5)

        assert "Iterations Run: 2" in result["summary"]
        assert "Max Iterations: 5" in result["summary"]

    @pytest.mark.asyncio
    async def test_empty_registry(self) -> None:
        """Test handles empty registry correctly."""
        generate_registry_summary = review_registry_module.generate_registry_summary

        registry = IssueRegistry(
            findings=[],
            current_iteration=0,
            max_iterations=3,
        )

        result = await generate_registry_summary(registry)

        assert result["stats"]["total"] == 0
        assert result["stats"]["fixed"] == 0
        assert "All findings resolved" in result["summary"]


class TestUpdateRegistryEdgeCases:
    """Additional edge case tests for update_issue_registry."""

    @pytest.mark.asyncio
    async def test_invalid_status_treated_as_deferred(self) -> None:
        """Test that invalid status string is treated as deferred (lines 573-579)."""
        update_registry = review_registry_module.update_issue_registry

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Test finding",
            description="Test",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        registry = IssueRegistry(
            findings=[TrackedFinding(finding=finding)],
            current_iteration=1,
            max_iterations=3,
        )

        # Create output with invalid status
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="INVALID_STATUS_VALUE",
                    justification="Test",
                    changes_made=None,
                ),
            ),
            summary=None,
        )

        result = await update_registry(registry, fixer_output)

        # Should be treated as deferred due to invalid status
        assert result.findings[0].status == FindingStatus.deferred


class TestCreateIssueRegistryEdgeCases:
    """Additional edge case tests for create_issue_registry."""

    @pytest.mark.asyncio
    async def test_deduplication_keeps_higher_severity(self) -> None:
        """Test deduplication keeps the finding with higher severity (line 429)."""
        create_issue_registry = review_registry_module.create_issue_registry

        # Two findings that are duplicates but with different severities
        spec_findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Same issue",
                "description": "Same description",
                "file_path": "src/test.py",
                "line_start": 10,
                "line_end": 15,
                "suggested_fix": None,
            },
        ]
        tech_findings = [
            {
                "id": "RT001",
                "severity": "critical",  # Higher severity
                "category": "correctness",
                "title": "Same issue",  # Same title
                "description": "Same description",
                "file_path": "src/test.py",  # Same file
                "line_start": 10,  # Same lines
                "line_end": 15,
                "suggested_fix": None,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,
            tech_findings=tech_findings,
        )

        # Should keep only one (the critical one)
        assert len(registry.findings) == 1
        assert registry.findings[0].finding.severity == Severity.critical

    @pytest.mark.asyncio
    async def test_non_overlapping_lines_not_duplicates(self) -> None:
        """Test findings with non-overlapping lines are not duplicates (line 311)."""
        create_issue_registry = review_registry_module.create_issue_registry

        spec_findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Same issue",
                "description": "Same description",
                "file_path": "src/test.py",
                "line_start": 10,
                "line_end": 15,
                "suggested_fix": None,
            },
        ]
        tech_findings = [
            {
                "id": "RT001",
                "severity": "major",
                "category": "correctness",
                "title": "Same issue",
                "description": "Same description",
                "file_path": "src/test.py",
                "line_start": 100,  # Different lines - no overlap
                "line_end": 110,
                "suggested_fix": None,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,
            tech_findings=tech_findings,
        )

        # Should keep both since lines don't overlap
        assert len(registry.findings) == 2

    @pytest.mark.asyncio
    async def test_handles_unparseable_finding(self) -> None:
        """Test handles malformed finding that raises exception (lines 402-403)."""
        create_issue_registry = review_registry_module.create_issue_registry

        # Include a finding with None where string is expected
        spec_findings = [
            None,  # This should be skipped
            {
                "id": "RS002",
                "severity": "major",
                "category": "correctness",
                "title": "Valid finding",
                "description": "Test",
                "file_path": "src/test.py",
                "line_start": 10,
                "line_end": 15,
                "suggested_fix": None,
            },
        ]

        registry = await create_issue_registry(
            spec_findings=spec_findings,  # type: ignore[arg-type]
            tech_findings=[],
        )

        # Should only have the valid finding
        assert len(registry.findings) == 1
        assert registry.findings[0].finding.id == "RS002"


class TestBuildIssueBodyEdgeCases:
    """Additional edge case tests for _build_issue_body."""

    @pytest.mark.asyncio
    async def test_includes_suggested_fix(self) -> None:
        """Test issue body includes suggested fix section (lines 783-786)."""
        build_issue_body = review_registry_module._build_issue_body

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Test finding",
            description="Description",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix="Use XYZ instead of ABC for better performance.",
            source="spec_reviewer",
        )
        tracked = TrackedFinding(finding=finding)

        body = build_issue_body(tracked, pr_number=123)

        assert "## Suggested Fix" in body
        assert "Use XYZ instead of ABC for better performance." in body

    @pytest.mark.asyncio
    async def test_includes_attempt_history(self) -> None:
        """Test issue body includes attempt history section (lines 790-803)."""
        build_issue_body = review_registry_module._build_issue_body

        finding = ReviewFinding(
            id="RS001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Test finding",
            description="Description",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            suggested_fix=None,
            source="spec_reviewer",
        )
        tracked = TrackedFinding(
            finding=finding,
            status=FindingStatus.blocked,
            attempts=[
                FixAttempt(
                    iteration=1,
                    timestamp=datetime(2024, 1, 1, 10, 0, 0),
                    outcome=FindingStatus.deferred,
                    justification="Working on it",
                    changes_made="Started refactoring",
                ),
                FixAttempt(
                    iteration=2,
                    timestamp=datetime(2024, 1, 1, 11, 0, 0),
                    outcome=FindingStatus.blocked,
                    justification="Blocked by external dependency",
                    changes_made=None,
                ),
            ],
        )

        body = build_issue_body(tracked, pr_number=123)

        assert "## Fix Attempt History" in body
        assert "Iteration 1" in body
        assert "Iteration 2" in body
        assert "Working on it" in body
        assert "Started refactoring" in body
        assert "Blocked by external dependency" in body
