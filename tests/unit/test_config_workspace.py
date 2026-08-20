"""Tests for the ``workspace:`` config block (057-isolated-bead-workspaces).

``WorkspaceConfig`` is the validated form of the raw ``workspace``
passthrough on ``MaverickConfig``; ``lookup_workspace_config`` is the
lenient loader that mirrors ``lookup_protection_config``/
``lookup_tiers_config``: malformed input degrades to defaults with a
warning, never a startup failure (research.md R10).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from maverick.config import MaverickConfig, WorkspaceConfig, load_config, lookup_workspace_config


class TestWorkspaceConfigDefaults:
    """``WorkspaceConfig`` defaults."""

    def test_defaults(self) -> None:
        config = WorkspaceConfig()
        assert config.enabled is False
        assert config.root == Path.home() / ".maverick" / "workspaces"

    def test_no_reuse_field(self) -> None:
        """`reuse` is not a config knob — each consumer's `IsolationPolicy`
        sets it programmatically (spec-chain: always True; fly: always
        False, load-bearing for its isolation guarantees). Exposing it here
        would let a user silently break fly's per-bead isolation contract."""
        assert not hasattr(WorkspaceConfig(), "reuse")

    def test_maverick_config_workspace_defaults_to_none(self) -> None:
        config = MaverickConfig()
        assert config.workspace is None

    def test_dead_fields_are_gone(self) -> None:
        assert not hasattr(WorkspaceConfig(), "setup")
        assert not hasattr(WorkspaceConfig(), "teardown")
        assert not hasattr(WorkspaceConfig(), "env_files")


class TestLookupWorkspaceConfig:
    """``lookup_workspace_config`` — lenient loader, `lookup_tiers_config` idiom."""

    def test_absent_block_returns_defaults_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = MaverickConfig()
        assert config.workspace is None

        with caplog.at_level(logging.WARNING):
            result = lookup_workspace_config(config)

        assert result == WorkspaceConfig()
        assert result.enabled is False
        assert "workspace_config" not in caplog.text

    def test_non_dict_shape_degrades_to_defaults_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = MaverickConfig.model_construct(workspace=["oops"])

        with caplog.at_level(logging.WARNING):
            result = lookup_workspace_config(config)

        assert result == WorkspaceConfig()
        assert "workspace_config_invalid_shape" in caplog.text

    def test_wrong_typed_field_degrades_to_defaults_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = MaverickConfig.model_construct(workspace={"enabled": "not-a-bool"})

        with caplog.at_level(logging.WARNING):
            result = lookup_workspace_config(config)

        assert result == WorkspaceConfig()
        assert "workspace_config_parse_failed" in caplog.text

    def test_valid_dict_parses(self) -> None:
        config = MaverickConfig.model_construct(
            workspace={"enabled": True, "root": "/tmp/workspaces"}
        )

        result = lookup_workspace_config(config)

        assert result.enabled is True
        assert result.root == Path("/tmp/workspaces")


class TestYamlAndEnvOverrides:
    """Loading through ``load_config`` / env-var precedence."""

    def test_yaml_full_block_round_trips(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
workspace:
  enabled: true
  root: /tmp/workspaces
"""
        )

        config = load_config()
        assert config.workspace == {
            "enabled": True,
            "root": "/tmp/workspaces",
        }

        parsed = lookup_workspace_config(config)
        assert parsed.enabled is True
        assert parsed.root == Path("/tmp/workspaces")

    def test_yaml_absent_block_stays_none(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
notifications:
  enabled: false
"""
        )

        config = load_config()
        assert config.workspace is None
        assert lookup_workspace_config(config) == WorkspaceConfig()

    def test_yaml_malformed_scalar_block_does_not_raise(
        self, clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A plain scalar (not a mapping) for ``workspace:`` must not fail
        config load — it degrades to defaults with a warning at
        ``lookup_workspace_config`` time.
        """
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
workspace: "not-a-dict"
"""
        )

        config = load_config()
        assert config.workspace == "not-a-dict"

        with caplog.at_level(logging.WARNING):
            result = lookup_workspace_config(config)

        assert result == WorkspaceConfig()
        assert "workspace_config_invalid_shape" in caplog.text


class TestExports:
    """``maverick.config.__all__`` surface."""

    def test_all_exports(self) -> None:
        from maverick import config as config_module

        for name in ("WorkspaceConfig", "lookup_workspace_config"):
            assert name in config_module.__all__
            assert hasattr(config_module, name)
