"""Configuration fixtures for Maverick tests.

This module provides pytest fixtures for creating MaverickConfig instances
with typical test values. These fixtures should be used throughout the test
suite to ensure consistent configuration setups.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from maverick.config import MaverickConfig, load_config


@pytest.fixture
def sample_config(
    clean_env: None, temp_dir: Path
) -> Generator[MaverickConfig, None, None]:
    """Create a sample MaverickConfig with typical test values.

    This fixture creates a temporary directory with a maverick.yaml file
    containing test configuration, then loads it using the standard config
    loading mechanism.

    Yields:
        MaverickConfig instance configured for testing with:
        - GitHub: test-org/test-repo with main branch
        - Notifications: disabled
        - Model: claude-sonnet-4-5-20250929 with 4096 max tokens, 0.5 temperature
        - Parallel: 2 max agents, 3 max tasks
        - Verbosity: info level
        - Default workflow configurations
    """
    # Change to temp directory so maverick.yaml is found
    original_cwd = os.getcwd()
    try:
        os.chdir(temp_dir)

        # Create maverick.yaml with test configuration
        config_content = """
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
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(config_content)

        # Load config using standard mechanism
        config = load_config()

        yield config
    finally:
        # Restore original working directory
        os.chdir(original_cwd)
