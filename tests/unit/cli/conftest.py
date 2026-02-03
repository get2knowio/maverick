"""Shared fixtures for CLI command tests.

This module provides shared fixtures and utilities for testing CLI commands.
The fixtures are scoped to the tests/unit/cli/ directory.

Common fixtures available from parent conftest.py:
- cli_runner: Click CLI test runner (from tests/conftest.py)
- temp_dir: Temporary directory for test files (from tests/conftest.py)
- clean_env: Clean environment without MAVERICK_ vars (from tests/conftest.py)
- sample_config_yaml: Sample YAML config content (from tests/conftest.py)
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def maverick_yaml(temp_dir: Path) -> Path:
    """Create a minimal maverick.yaml in the temp directory."""
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("github:\n  owner: test-org\n  repo: test-repo\n")
    return config_file
