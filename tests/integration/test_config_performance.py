from __future__ import annotations

import time
from pathlib import Path

import pytest


class TestConfigPerformance:
    """Performance tests for configuration loading (SC-005)."""

    def test_config_loading_under_100ms(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        SC-005: Configuration loading completes in under 100ms.

        This test verifies that the full configuration loading process
        (user config + project config + env vars + defaults) completes
        within the 100ms threshold.
        """
        import os

        os.chdir(temp_dir)

        # Create a realistic config scenario
        user_config_dir = temp_dir / ".config" / "maverick"
        user_config_dir.mkdir(parents=True)
        user_config_path = user_config_dir / "config.yaml"
        user_config_path.write_text("""
github:
  owner: "test-org"
notifications:
  server: "https://ntfy.example.com"
model:
  max_tokens: 4096
verbosity: "info"
""")

        project_config_path = temp_dir / "maverick.yaml"
        project_config_path.write_text("""
github:
  owner: "project-org"
  repo: "test-repo"
model:
  max_tokens: 8192
""")

        os.environ["MAVERICK_MODEL__TEMPERATURE"] = "0.5"
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import load_config

        # Measure config loading time
        start = time.perf_counter()
        config = load_config()
        elapsed = time.perf_counter() - start

        # Verify config loaded successfully
        assert config.github.owner == "project-org"
        assert config.github.repo == "test-repo"

        # Verify performance requirement
        assert elapsed < 0.1, (
            f"Config loading took {elapsed * 1000:.2f}ms, "
            f"expected < 100ms (SC-005 requirement)"
        )

    def test_config_loading_warm_cache_under_100ms(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that repeated config loading (warm cache scenario) is fast.

        Note: This is for the second and subsequent loads in the same process.
        """
        import os

        os.chdir(temp_dir)

        project_config_path = temp_dir / "maverick.yaml"
        project_config_path.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
""")

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import load_config

        # First load (cold)
        load_config()

        # Second load (warm) - should be even faster
        start = time.perf_counter()
        config = load_config()
        elapsed = time.perf_counter() - start

        assert config.github.owner == "test-org"
        assert elapsed < 0.1, (
            f"Warm config loading took {elapsed * 1000:.2f}ms, expected < 100ms"
        )

    def test_config_loading_defaults_only_under_100ms(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that config loading with defaults only is fast.

        This is the simplest scenario (no user or project config files).
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import load_config

        # Measure defaults-only config loading
        start = time.perf_counter()
        config = load_config()
        elapsed = time.perf_counter() - start

        assert config.github.owner is None  # Verify defaults
        assert elapsed < 0.1, (
            f"Defaults-only config loading took {elapsed * 1000:.2f}ms, "
            f"expected < 100ms"
        )
