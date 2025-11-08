"""Pytest configuration and shared fixtures.

Provides common test fixtures and Temporal test environment setup
for unit and integration tests.
"""

from pathlib import Path

import pytest


@pytest.fixture
def sample_fixture() -> str:
    """Example fixture for testing.

    Returns:
        A sample string value
    """
    return "test_value"


# Placeholder for Temporal test environment bootstrap
# TODO: Add Temporal testing utilities once temporalio is installed
# Example structure:
# @pytest.fixture
# async def temporal_env() -> Generator:
#     """Set up Temporal test environment."""
#     from temporalio.testing import WorkflowEnvironment
#     async with WorkflowEnvironment.start() as env:
#         yield env


@pytest.fixture
def mock_subprocess_success(monkeypatch):
    """Mock subprocess.run to return successful results.

    Useful for testing activities that execute external commands
    without actually running them.
    """
    import subprocess

    def mock_run(*args, **kwargs):
        """Mock successful subprocess execution."""
        result = subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=0,
            stdout="mock success output",
            stderr="",
        )
        return result

    monkeypatch.setattr("subprocess.run", mock_run)
    return mock_run


@pytest.fixture
def mock_subprocess_failure(monkeypatch):
    """Mock subprocess.run to return failure results.

    Useful for testing error handling in activities.
    """
    import subprocess

    def mock_run(*args, **kwargs):
        """Mock failed subprocess execution."""
        result = subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=1,
            stdout="",
            stderr="mock error output",
        )
        return result

    monkeypatch.setattr("subprocess.run", mock_run)
    return mock_run


@pytest.fixture(scope="session")
def phase_automation_fixtures_dir() -> Path:
    """Return base directory for phase automation markdown fixtures."""

    return Path(__file__).parent / "fixtures" / "phase_automation"


@pytest.fixture
def sample_tasks_md_path(phase_automation_fixtures_dir: Path) -> Path:
    """Path to the baseline phase automation tasks markdown file."""

    return phase_automation_fixtures_dir / "sample_tasks.md"


@pytest.fixture
def sample_tasks_md_content(sample_tasks_md_path: Path) -> str:
    """Load canonical sample phase automation tasks markdown content."""

    return sample_tasks_md_path.read_text(encoding="utf-8")


@pytest.fixture
def invalid_tasks_md_path(phase_automation_fixtures_dir: Path) -> Path:
    """Path to markdown fixture missing phase headings for negative tests."""

    return phase_automation_fixtures_dir / "invalid_missing_phase.md"


@pytest.fixture
def invalid_tasks_md_content(invalid_tasks_md_path: Path) -> str:
    """Load markdown missing phase headings for parser validation tests."""

    return invalid_tasks_md_path.read_text(encoding="utf-8")


@pytest.fixture
def gh_cli_stub():
    """Provide GhCliStubHelper for mocking gh CLI commands in tests.

    Returns:
        GhCliStubHelper instance configured for PR CI automation testing

    Example:
        def test_pr_view(gh_cli_stub, monkeypatch):
            gh_cli_stub.stub_pr_view(pr_number=123, state="OPEN")
            # Mock subprocess to return gh_cli_stub responses
    """
    from tests.fixtures.pr_ci_automation.gh_cli_stub import GhCliStubHelper

    return GhCliStubHelper()
