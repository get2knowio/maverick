"""Example configuration tests demonstrating testing patterns.

This module shows how to use configuration fixtures and test patterns
for configuration validation. Use these patterns as reference when writing
configuration-related tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from maverick.config import MaverickConfig, load_config


class TestConfigPatterns:
    """Example tests demonstrating configuration testing patterns."""

    def test_sample_config_fixture(self, sample_config: MaverickConfig) -> None:
        """Test that sample_config returns valid MaverickConfig.

        This demonstrates:
        - Using the sample_config fixture
        - Basic type and structure validation
        - Verifying the fixture provides a working config instance

        The sample_config fixture automatically uses clean_env and temp_dir
        internally, so you get a clean environment for testing.
        """
        # sample_config is properly typed and instantiated
        assert isinstance(sample_config, MaverickConfig)

        # All required nested config objects are present
        assert sample_config.github is not None
        assert sample_config.notifications is not None
        assert sample_config.model is not None
        assert sample_config.parallel is not None

    def test_config_github_values(self, sample_config: MaverickConfig) -> None:
        """Test GitHub configuration values.

        This demonstrates:
        - Accessing nested configuration values
        - Verifying specific test values from the fixture
        """
        # GitHub config should have test values from fixture
        assert sample_config.github.owner == "test-org"
        assert sample_config.github.repo == "test-repo"
        assert sample_config.github.default_branch == "main"

    def test_config_model_values(self, sample_config: MaverickConfig) -> None:
        """Test model configuration values.

        This demonstrates:
        - Testing model settings
        - Verifying numeric constraints
        """
        # Model config should have expected test values
        assert sample_config.model.model_id == "claude-sonnet-4-5-20250929"
        assert sample_config.model.max_tokens == 4096
        assert sample_config.model.temperature == 0.5

        # Verify temperature is within valid range
        assert 0.0 <= sample_config.model.temperature <= 1.0

    def test_config_parallel_values(self, sample_config: MaverickConfig) -> None:
        """Test parallel execution settings.

        This demonstrates:
        - Testing concurrency configuration
        - Validating numeric constraints
        """
        # Parallel config should have test values
        assert sample_config.parallel.max_agents == 2
        assert sample_config.parallel.max_tasks == 3

        # Verify values are positive
        assert sample_config.parallel.max_agents > 0
        assert sample_config.parallel.max_tasks > 0

    def test_using_clean_env_and_temp_dir_directly(
        self, clean_env: None, temp_dir: Path
    ) -> None:
        """Test using clean_env and temp_dir fixtures directly.

        This demonstrates:
        - Using clean_env to ensure no MAVERICK_* environment variables
        - Using temp_dir to create temporary configuration files
        - Loading config from a custom YAML file
        - Manually testing configuration loading behavior

        Use this pattern when you need more control than sample_config provides.
        """
        # Change to temp directory
        os.chdir(temp_dir)

        # Create a custom config file with specific values
        config_content = """
github:
  owner: "custom-org"
  repo: "custom-repo"

model:
  max_tokens: 2048
  temperature: 0.7
"""
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(config_content)

        # Load the config
        config = load_config()

        # Verify custom values were loaded
        assert config.github.owner == "custom-org"
        assert config.github.repo == "custom-repo"
        assert config.model.max_tokens == 2048
        assert config.model.temperature == 0.7

        # Verify no environment variables interfered (thanks to clean_env)
        # This would fail if there were MAVERICK_* env vars set
        assert not any(key.startswith("MAVERICK_") for key in os.environ)
