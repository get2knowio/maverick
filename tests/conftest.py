"""Pytest configuration and shared fixtures.

Provides common test fixtures and Temporal test environment setup
for unit and integration tests.
"""

import pytest
from typing import Generator


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
