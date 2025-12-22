"""Sample agent response fixtures for testing.

This module provides fixtures that return sample agent response data
structures for use in unit tests. These fixtures create realistic
response objects that match the actual return types from agents.

Provides:
- sample_review_response: Typical code review success response
- sample_implementation_response: Typical implementation success response
- sample_error_response: Error response with failure details
"""

from __future__ import annotations

import pytest

from maverick.models.implementation import (
    ChangeType,
    FileChange,
    ImplementationResult,
    TaskResult,
    TaskStatus,
)
from maverick.models.review import ReviewResult


@pytest.fixture
def sample_review_response() -> ReviewResult:
    """Factory fixture for a typical successful code review response.

    Returns:
        ReviewResult with no findings, indicating a clean review.

    Example:
        >>> def test_review(sample_review_response):
        ...     result = sample_review_response
        ...     assert result.success is True
        ...     assert result.files_reviewed == 3
        ...     assert len(result.findings) == 0
    """
    return ReviewResult(
        success=True,
        findings=[],
        files_reviewed=3,
        summary="Reviewed 3 files, no issues found",
        truncated=False,
        output="",
        metadata={
            "branch": "feature/test-branch",
            "base_branch": "main",
            "duration_ms": 1500,
            "binary_files_excluded": 0,
            "timestamp": "2025-12-17T12:00:00Z",
        },
        errors=[],
    )


@pytest.fixture
def sample_implementation_response() -> ImplementationResult:
    """Factory fixture for a typical successful implementation response.

    Returns:
        ImplementationResult with completed tasks and file changes.

    Example:
        >>> def test_implementation(sample_implementation_response):
        ...     result = sample_implementation_response
        ...     assert result.success is True
        ...     assert result.tasks_completed == 2
        ...     assert len(result.files_changed) == 1
    """
    return ImplementationResult(
        success=True,
        tasks_completed=2,
        tasks_failed=0,
        tasks_skipped=0,
        task_results=[
            TaskResult(
                task_id="T001",
                status=TaskStatus.COMPLETED,
                files_changed=[
                    FileChange(
                        file_path="src/test.py",
                        change_type=ChangeType.MODIFIED,
                        lines_added=10,
                        lines_removed=2,
                    )
                ],
                tests_added=["tests/test_file.py"],
                commit_sha="abc123def456",
                duration_ms=2000,
            ),
            TaskResult(
                task_id="T002",
                status=TaskStatus.COMPLETED,
                files_changed=[],
                tests_added=[],
                commit_sha="def456abc123",
                duration_ms=1500,
            ),
        ],
        files_changed=[
            FileChange(
                file_path="src/test.py",
                change_type=ChangeType.MODIFIED,
                lines_added=10,
                lines_removed=2,
            )
        ],
        commits=["abc123def456", "def456abc123"],
        validation_passed=True,
        output="Implementation complete",
        metadata={
            "branch": "feature/test-implementation",
            "duration_ms": 3500,
            "dry_run": False,
        },
        errors=[],
    )


@pytest.fixture
def sample_error_response() -> ImplementationResult:
    """Factory fixture for a typical error response from an agent.

    Returns:
        ImplementationResult with failure status and error details.

    Example:
        >>> def test_error_handling(sample_error_response):
        ...     result = sample_error_response
        ...     assert result.success is False
        ...     assert "Test error message" in result.errors
        ...     assert result.tasks_failed == 1
    """
    return ImplementationResult(
        success=False,
        tasks_completed=0,
        tasks_failed=1,
        tasks_skipped=0,
        task_results=[
            TaskResult(
                task_id="T001",
                status=TaskStatus.FAILED,
                error="Test error message",
                duration_ms=500,
            )
        ],
        files_changed=[],
        commits=[],
        validation_passed=False,
        output="",
        metadata={
            "branch": "feature/test-error",
            "duration_ms": 500,
            "dry_run": False,
        },
        errors=["Test error message"],
    )
