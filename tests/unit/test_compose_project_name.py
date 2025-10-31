"""Tests for Docker Compose project name sanitization."""

import pytest

from src.models.compose import ComposeEnvironment


def test_project_name_validation_lowercase():
    """Project names must be lowercase."""
    env = ComposeEnvironment(
        project_name="maverick-test-workflow-run123",
        target_service="app",
        health_status="healthy",
        container_ids={"app": "abc123"},
        started_at="2025-10-30T12:00:00Z",
    )
    assert env.project_name == "maverick-test-workflow-run123"


def test_project_name_with_hyphens_and_underscores():
    """Project names can contain hyphens and underscores."""
    env = ComposeEnvironment(
        project_name="maverick-test_workflow-123_456",
        target_service="app",
        health_status="healthy",
        container_ids={"app": "abc123"},
        started_at="2025-10-30T12:00:00Z",
    )
    assert env.project_name == "maverick-test_workflow-123_456"


def test_project_name_must_start_with_alphanumeric():
    """Project names must start with letter or number."""
    # Starts with letter - valid
    env = ComposeEnvironment(
        project_name="maverick-test",
        target_service="app",
        health_status="healthy",
        container_ids={"app": "abc123"},
        started_at="2025-10-30T12:00:00Z",
    )
    assert env.project_name == "maverick-test"

    # Starts with number after prefix - valid
    env2 = ComposeEnvironment(
        project_name="maverick-1test",
        target_service="app",
        health_status="healthy",
        container_ids={"app": "abc123"},
        started_at="2025-10-30T12:00:00Z",
    )
    assert env2.project_name == "maverick-1test"


def test_project_name_rejects_uppercase():
    """Project names must not contain uppercase letters."""
    with pytest.raises(ValueError, match="Invalid project name format"):
        ComposeEnvironment(
            project_name="Maverick-Test-Workflow",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )


def test_project_name_rejects_periods():
    """Project names must not contain periods."""
    with pytest.raises(ValueError, match="Invalid project name format"):
        ComposeEnvironment(
            project_name="maverick-test.workflow",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )


def test_project_name_rejects_special_chars():
    """Project names must not contain special characters."""
    with pytest.raises(ValueError, match="Invalid project name format"):
        ComposeEnvironment(
            project_name="maverick-test@workflow",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )


def test_project_name_rejects_starting_with_hyphen():
    """Project names must not start with hyphen."""
    with pytest.raises(ValueError, match="Invalid project name format"):
        ComposeEnvironment(
            project_name="-maverick-test",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )


def test_project_name_rejects_starting_with_underscore():
    """Project names must not start with underscore."""
    with pytest.raises(ValueError, match="Invalid project name format"):
        ComposeEnvironment(
            project_name="_maverick-test",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )


def test_sanitized_workflow_ids():
    """Short deterministic hash format should be valid."""
    # Simulate hash-based project name (8 hex characters)
    env = ComposeEnvironment(
        project_name="maverick-a1b2c3d4",
        target_service="app",
        health_status="healthy",
        container_ids={"app": "abc123"},
        started_at="2025-10-30T12:00:00Z",
    )
    assert "." not in env.project_name
    assert ":" not in env.project_name
    assert len(env.project_name) == 17  # "maverick-" (9) + 8 chars = 17
    assert env.project_name.startswith("maverick-")


def test_project_name_must_start_with_maverick():
    """Project names must start with 'maverick-' prefix."""
    with pytest.raises(ValueError, match="must start with 'maverick-'"):
        ComposeEnvironment(
            project_name="other-a1b2c3d4",
            target_service="app",
            health_status="healthy",
            container_ids={"app": "abc123"},
            started_at="2025-10-30T12:00:00Z",
        )
