from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def test_load_defaults_when_no_config(clean_env: None, temp_dir: Path) -> None:
    """Test that defaults are used when no config file exists."""
    import os

    os.chdir(temp_dir)

    from maverick.config import MaverickConfig, load_config

    config = load_config()
    assert isinstance(config, MaverickConfig)
    # Check defaults
    assert config.model.model_id == "sonnet"
    assert config.model.max_tokens == 64000
    assert config.parallel.max_agents == 3
    assert config.verbosity == "warning"


def test_load_project_config(clean_env: None, temp_dir: Path, sample_config_yaml: str) -> None:
    """Test loading configuration from maverick.yaml."""
    import os

    os.chdir(temp_dir)

    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(sample_config_yaml)

    from maverick.config import load_config

    config = load_config()
    assert config.github.owner == "test-org"
    assert config.github.repo == "test-repo"
    assert config.model.max_tokens == 4096
    assert config.verbosity == "info"


def test_env_var_overrides(clean_env: None, temp_dir: Path) -> None:
    """Test that MAVERICK_* environment variables override config."""
    import os

    os.chdir(temp_dir)
    os.environ["MAVERICK_GITHUB__OWNER"] = "env-org"
    os.environ["MAVERICK_MODEL__MAX_TOKENS"] = "2048"

    from maverick.config import load_config

    config = load_config()
    assert config.github.owner == "env-org"
    assert config.model.max_tokens == 2048


def test_invalid_config_raises_config_error(clean_env: None, temp_dir: Path) -> None:
    """Test that invalid configuration raises ConfigError."""
    import os

    os.chdir(temp_dir)

    invalid_yaml = """
parallel:
  max_agents: 15  # Invalid: max is 10
"""
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(invalid_yaml)

    from maverick.config import load_config
    from maverick.exceptions import ConfigError

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "max_agents" in str(exc_info.value.message) or (
        exc_info.value.field == "parallel.max_agents"
    )


def test_unknown_keys_ignored(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that unknown configuration keys are ignored."""
    import logging
    import os

    os.chdir(temp_dir)

    yaml_with_unknown = """
github:
  owner: "test-org"
unknown_section:
  foo: "bar"
"""
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(yaml_with_unknown)

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Config should load successfully
    assert config.github.owner == "test-org"
    # Optionally check for warning log (implementation may or may not log)


def test_secrets_not_exposed_from_yaml(clean_env: None, temp_dir: Path) -> None:
    """Test that secret-like fields are not loaded from YAML files."""
    import os

    os.chdir(temp_dir)

    yaml_with_secrets = """
github:
  owner: "test-org"
  api_key: "secret-key-123"
  token: "secret-token"
  password: "secret-password"
"""
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(yaml_with_secrets)

    from maverick.config import load_config

    config = load_config()
    # These secret fields should not exist on the config model
    assert not hasattr(config.github, "api_key")
    assert not hasattr(config.github, "token")
    assert not hasattr(config.github, "password")


def test_load_user_config(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test loading user configuration from ~/.config/maverick/config.yaml."""
    import os

    os.chdir(temp_dir)

    # Create fake user config directory
    user_config_dir = temp_dir / ".config" / "maverick"
    user_config_dir.mkdir(parents=True)
    user_config_path = user_config_dir / "config.yaml"
    user_config_path.write_text("""
notifications:
  server: "https://custom-ntfy.example.com"
model:
  temperature: 0.3
""")

    # Patch Path.home() to return temp_dir
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.config import load_config

    config = load_config()
    assert config.notifications.server == "https://custom-ntfy.example.com"
    assert config.model.temperature == 0.3


def test_project_config_overrides_user_config(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that project config overrides user config."""
    import os

    os.chdir(temp_dir)

    # Create user config
    user_config_dir = temp_dir / ".config" / "maverick"
    user_config_dir.mkdir(parents=True)
    user_config_path = user_config_dir / "config.yaml"
    user_config_path.write_text("""
github:
  owner: "user-org"
model:
  max_tokens: 4096
""")

    # Create project config that overrides some settings
    project_config_path = temp_dir / "maverick.yaml"
    project_config_path.write_text("""
github:
  owner: "project-org"
""")

    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.config import load_config

    config = load_config()
    # project config should override user config
    assert config.github.owner == "project-org"
    # user config should still apply for non-overridden values
    assert config.model.max_tokens == 4096


def test_merge_partial_configs(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test merging partial user and project configs."""
    import os

    os.chdir(temp_dir)

    # User config sets some values
    user_config_dir = temp_dir / ".config" / "maverick"
    user_config_dir.mkdir(parents=True)
    user_config_path = user_config_dir / "config.yaml"
    user_config_path.write_text("""
notifications:
  topic: "user-notifications"
model:
  temperature: 0.2
""")

    # Project config sets different values
    project_config_path = temp_dir / "maverick.yaml"
    project_config_path.write_text("""
github:
  repo: "my-project"
verbosity: "debug"
""")

    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.config import load_config

    config = load_config()
    # Values from user config
    assert config.notifications.topic == "user-notifications"
    assert config.model.temperature == 0.2
    # Values from project config
    assert config.github.repo == "my-project"
    assert config.verbosity == "debug"
    # Defaults for unset values
    assert config.model.model_id == "sonnet"


def test_empty_config_file_uses_defaults_with_warning(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that empty config file uses defaults and logs a warning."""
    import logging
    import os

    os.chdir(temp_dir)

    # Create an empty config file
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text("")

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Should use defaults
    assert config.model.model_id == "sonnet"
    assert config.model.max_tokens == 64000
    assert config.parallel.max_agents == 3

    # Should log a warning
    assert any("empty" in record.message.lower() for record in caplog.records)
    assert any("using defaults" in record.message.lower() for record in caplog.records)


def test_empty_config_with_comments_uses_defaults(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that config file with only comments/whitespace uses defaults."""
    import logging
    import os

    os.chdir(temp_dir)

    # Create config file with only comments and whitespace
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text("""
# This is a comment

  # Another comment

""")

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Should use defaults
    assert config.model.model_id == "sonnet"
    assert config.verbosity == "warning"

    # Should log a warning
    assert any("empty" in record.message.lower() for record in caplog.records)


def test_invalid_env_var_value_produces_error(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that invalid env var values produce clear validation errors."""
    import os

    os.chdir(temp_dir)
    os.environ["MAVERICK_MODEL__MAX_TOKENS"] = "not-a-number"
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.config import load_config
    from maverick.exceptions import ConfigError

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "max_tokens" in str(exc_info.value.message).lower() or (
        exc_info.value.field == "model.max_tokens"
    )


def test_missing_user_config_directory_works(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that missing user config directory doesn't cause errors."""
    import os

    os.chdir(temp_dir)
    # Don't create .config/maverick/ directory
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.config import load_config

    config = load_config()
    # Should use defaults without error
    assert config.model.model_id == "sonnet"


def test_notification_enabled_without_topic_logs_warning(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that enabling notifications without a topic logs a warning."""
    import logging
    import os

    os.chdir(temp_dir)

    # Create config with notifications enabled but no topic
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text("""
notifications:
  enabled: true
""")

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Config should load successfully
    assert config.notifications.enabled is True
    assert config.notifications.topic is None

    # Should log a warning
    assert any("topic" in record.message.lower() for record in caplog.records)
    assert any("enabled" in record.message.lower() for record in caplog.records)


def test_notification_enabled_with_topic_no_warning(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that enabling notifications with a topic does not log a warning."""
    import logging
    import os

    os.chdir(temp_dir)

    # Create config with notifications enabled with a topic
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text("""
notifications:
  enabled: true
  topic: "my-notifications"
""")

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Config should load successfully
    assert config.notifications.enabled is True
    assert config.notifications.topic == "my-notifications"

    # Should not log a warning about notifications
    notification_warnings = [
        record
        for record in caplog.records
        if "notifications" in record.message.lower() and "topic" in record.message.lower()
    ]
    assert len(notification_warnings) == 0


def test_notification_disabled_without_topic_no_warning(
    clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that disabled notifications without a topic does not log a warning."""
    import logging
    import os

    os.chdir(temp_dir)

    # Create config with notifications disabled (default)
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text("""
notifications:
  enabled: false
""")

    from maverick.config import load_config

    with caplog.at_level(logging.WARNING):
        config = load_config()

    # Config should load successfully
    assert config.notifications.enabled is False
    assert config.notifications.topic is None

    # Should not log a warning about notifications
    notification_warnings = [
        record
        for record in caplog.records
        if "notifications" in record.message.lower() and "topic" in record.message.lower()
    ]
    assert len(notification_warnings) == 0


class TestMaverickConfigSteps:
    """Tests for MaverickConfig.steps field (033-step-config)."""

    def test_steps_default_empty_dict(self, clean_env: None, temp_dir: Path) -> None:
        """steps field defaults to empty dict."""
        import os

        os.chdir(temp_dir)
        from maverick.config import MaverickConfig

        config = MaverickConfig()
        assert config.steps == {}

    def test_steps_with_valid_step_config(self, clean_env: None, temp_dir: Path) -> None:
        """steps field accepts valid StepConfig values from YAML."""
        import os

        os.chdir(temp_dir)
        from maverick.types import AutonomyLevel

        yaml_content = """
steps:
  review:
    autonomy: consultant
    timeout: 300
  implement:
    max_retries: 3
"""
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(yaml_content)

        from maverick.config import load_config

        config = load_config()
        assert "review" in config.steps
        assert config.steps["review"].autonomy == AutonomyLevel.CONSULTANT
        assert config.steps["review"].timeout == 300
        assert config.steps["implement"].max_retries == 3

    def test_steps_from_yaml(self, clean_env: None, temp_dir: Path) -> None:
        """steps field loads from maverick.yaml."""
        import os

        os.chdir(temp_dir)

        yaml_content = """
steps:
  review_code:
    autonomy: consultant
    timeout: 300
  implement_feature:
    max_retries: 3
"""
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(yaml_content)

        from maverick.config import load_config

        config = load_config()
        assert "review_code" in config.steps
        assert config.steps["review_code"].timeout == 300
        assert "implement_feature" in config.steps
        assert config.steps["implement_feature"].max_retries == 3

    def test_steps_invalid_value_rejected(self, clean_env: None, temp_dir: Path) -> None:
        """steps field rejects invalid StepConfig values."""
        import os

        os.chdir(temp_dir)

        yaml_content = """
steps:
  review_code:
    temperature: 5.0
"""
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(yaml_content)

        from maverick.config import load_config
        from maverick.exceptions import ConfigError

        with pytest.raises(ConfigError):
            load_config()


class TestLookupActorConfig:
    """Tests for the actors.<workflow>.<actor> resolver helper."""

    def _config_with_actors(self, actors: dict) -> Any:
        """Build a MaverickConfig with a populated actors block."""
        from maverick.config import MaverickConfig

        cfg = MaverickConfig()
        # actors is dict[str, dict[str, Any]] — assign directly.
        cfg.actors = actors
        return cfg

    def test_returns_none_when_workflow_missing(self) -> None:
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors({})
        assert lookup_actor_config(cfg, "fly-beads", "implementer") is None

    def test_returns_none_when_actor_missing(self) -> None:
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors({"fly": {}})
        assert lookup_actor_config(cfg, "fly-beads", "implementer") is None

    def test_workflow_name_mapped_to_short_key(self) -> None:
        """`fly-beads` (internal) → `fly` (user-facing actors block key)."""
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors(
            {
                "fly": {
                    "implementer": {
                        "provider": "copilot",
                        "model_id": "gpt-5.3-codex",
                    },
                },
            }
        )
        result = lookup_actor_config(cfg, "fly-beads", "implementer")
        assert result is not None
        assert result.provider == "copilot"
        assert result.model_id == "gpt-5.3-codex"

    def test_generate_flight_plan_maps_to_plan(self) -> None:
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors({"plan": {"scopist": {"provider": "gemini"}}})
        result = lookup_actor_config(cfg, "generate-flight-plan", "scopist")
        assert result is not None
        assert result.provider == "gemini"

    def test_refuel_maverick_maps_to_refuel(self) -> None:
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors(
            {"refuel": {"decomposer": {"provider": "claude", "model_id": "opus"}}}
        )
        result = lookup_actor_config(cfg, "refuel-maverick", "decomposer")
        assert result is not None
        assert result.model_id == "opus"

    def test_unknown_workflow_falls_back_to_literal_key(self) -> None:
        """Unmapped workflow_name lookups try the literal key — useful
        for ad-hoc workflows that haven't been added to the map."""
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors({"custom-workflow": {"agent": {"provider": "claude"}}})
        result = lookup_actor_config(cfg, "custom-workflow", "agent")
        assert result is not None
        assert result.provider == "claude"

    def test_tiers_field_preserved_on_actor_config(self) -> None:
        """`tiers:` is structurally accepted on ActorConfig (consumed elsewhere)."""
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors(
            {
                "fly": {
                    "implementer": {
                        "provider": "copilot",
                        "tiers": {
                            "trivial": {"provider": "opencode"},
                        },
                    },
                },
            }
        )
        result = lookup_actor_config(cfg, "fly-beads", "implementer")
        assert result is not None
        assert result.provider == "copilot"
        assert result.tiers == {"trivial": {"provider": "opencode"}}

    def test_malformed_entry_returns_none(self) -> None:
        """A validation error returns None and logs a warning — startup doesn't crash."""
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors(
            {
                "fly": {
                    "implementer": {"temperature": 99.0},  # > 1.0 cap
                },
            }
        )
        assert lookup_actor_config(cfg, "fly-beads", "implementer") is None

    def test_non_dict_entry_returns_none(self) -> None:
        """A YAML scalar where a mapping was expected is treated as absent."""
        from maverick.config import lookup_actor_config

        cfg = self._config_with_actors({"fly": {"implementer": "not-a-mapping"}})
        assert lookup_actor_config(cfg, "fly-beads", "implementer") is None


class TestLoadConfigCustomPath:
    """Tests for load_config(config_path) respecting the provided path."""

    def test_custom_config_path_is_loaded(self, clean_env: None, temp_dir: Path) -> None:
        """load_config(custom_path) loads from the custom file, not maverick.yaml."""
        import os

        os.chdir(temp_dir)

        # Write a default maverick.yaml with one value
        (temp_dir / "maverick.yaml").write_text(
            """
github:
  owner: "default-org"
"""
        )

        # Write a custom-named config with a different value
        custom_path = temp_dir / "maverick-copilot.yaml"
        custom_path.write_text(
            """
github:
  owner: "copilot-org"
model:
  max_tokens: 8192
"""
        )

        from maverick.config import load_config

        config = load_config(config_path=custom_path)
        # Should load from the custom file, NOT maverick.yaml
        assert config.github.owner == "copilot-org"
        assert config.model.max_tokens == 8192

    def test_default_path_still_works(self, clean_env: None, temp_dir: Path) -> None:
        """load_config() without a path still loads maverick.yaml from cwd."""
        import os

        os.chdir(temp_dir)

        (temp_dir / "maverick.yaml").write_text(
            """
github:
  owner: "cwd-org"
"""
        )

        from maverick.config import load_config

        config = load_config()
        assert config.github.owner == "cwd-org"

    def test_custom_path_nonexistent_uses_defaults(self, clean_env: None, temp_dir: Path) -> None:
        """load_config(missing_path) uses defaults when file doesn't exist."""
        import os

        os.chdir(temp_dir)

        from maverick.config import load_config

        config = load_config(config_path=temp_dir / "nonexistent.yaml")
        assert config.model.model_id == "sonnet"
        assert config.model.max_tokens == 64000
