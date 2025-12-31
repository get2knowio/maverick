from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestConfigLoadingIntegration:
    """Integration tests for the full configuration loading flow."""

    def test_full_config_hierarchy(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete config hierarchy: defaults -> user -> project -> env."""
        os.chdir(temp_dir)

        # 1. Create user config (some values)
        user_config_dir = temp_dir / ".config" / "maverick"
        user_config_dir.mkdir(parents=True)
        user_config_path = user_config_dir / "config.yaml"
        user_config_path.write_text("""
github:
  owner: "user-level-org"
notifications:
  server: "https://user-ntfy.example.com"
model:
  max_tokens: 2048
  temperature: 0.1
verbosity: "info"
""")

        # 2. Create project config (overrides some user values)
        project_config_path = temp_dir / "maverick.yaml"
        project_config_path.write_text("""
github:
  owner: "project-level-org"
  repo: "my-repo"
model:
  max_tokens: 4096
""")

        # 3. Set environment variables (highest priority)
        os.environ["MAVERICK_MODEL__MAX_TOKENS"] = "8192"

        # Patch home directory
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import load_config

        config = load_config()

        # Verify hierarchy:
        # - github.owner: project overrides user -> "project-level-org"
        assert config.github.owner == "project-level-org"
        # - github.repo: only in project -> "my-repo"
        assert config.github.repo == "my-repo"
        # - notifications.server: only in user -> "https://user-ntfy.example.com"
        assert config.notifications.server == "https://user-ntfy.example.com"
        # - model.max_tokens: env overrides project -> 8192
        assert config.model.max_tokens == 8192
        # - model.temperature: only in user -> 0.1
        assert config.model.temperature == 0.1
        # - verbosity: only in user -> "info"
        assert config.verbosity == "info"
        # - parallel.max_agents: default -> 3
        assert config.parallel.max_agents == 3

    def test_defaults_only(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that defaults work when no config files exist."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import MaverickConfig, load_config

        config = load_config()

        # All defaults should be applied
        assert isinstance(config, MaverickConfig)
        assert config.github.owner is None
        assert config.github.default_branch == "main"
        assert config.notifications.enabled is False
        assert config.model.model_id == "claude-sonnet-4-5-20250929"
        assert config.model.max_tokens == 64000
        assert config.parallel.max_agents == 3
        assert config.verbosity == "warning"
