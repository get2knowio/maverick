from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from click.testing import CliRunner

# Register fixture plugins from tests/fixtures/
pytest_plugins = [
    "tests.fixtures.agents",
    "tests.fixtures.config",
    "tests.fixtures.github",
    "tests.fixtures.responses",
    "tests.fixtures.runners",
]


@pytest.fixture(autouse=True)
def configure_test_logging() -> Generator[None, None, None]:
    """Configure structlog for test environment.

    This fixture runs automatically for all tests to ensure logging
    is properly configured to output to stderr (not stdout) and
    suppress verbose log output during tests.
    """
    from maverick.logging import configure_logging

    # Configure logging to use stderr at WARNING level to reduce noise
    # and prevent log output from mixing with test stdout
    configure_logging(level=logging.WARNING)
    yield


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create a temporary directory for test files.

    Also saves and restores the current working directory to prevent
    tests that use os.chdir() from affecting other tests.
    """
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
    os.chdir(original_cwd)


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Remove all MAVERICK_ environment variables for clean testing."""
    original_env = os.environ.copy()
    # Remove any existing MAVERICK_ env vars
    for key in list(os.environ.keys()):
        if key.startswith("MAVERICK_"):
            del os.environ[key]
    yield
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def sample_config_yaml() -> str:
    """Return sample maverick.yaml content for testing."""
    return """
github:
  owner: "test-org"
  repo: "test-repo"
  default_branch: "main"

notifications:
  enabled: false

model:
  model_id: "claude-sonnet-4-5-20250929"
  max_tokens: 4096
  temperature: 0.5

parallel:
  max_agents: 2
  max_tasks: 3

verbosity: "info"
"""


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner.

    Returns:
        CliRunner instance for testing Click commands.

    Example:
        >>> def test_version(cli_runner):
        ...     from maverick.main import cli
        ...     result = cli_runner.invoke(cli, ["--version"])
        ...     assert result.exit_code == 0
    """
    from click.testing import CliRunner

    return CliRunner()
