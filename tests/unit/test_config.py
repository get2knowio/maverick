from __future__ import annotations

from pathlib import Path

import pytest


def test_load_defaults_when_no_config(clean_env: None, temp_dir: Path) -> None:
    """Test that defaults are used when no config file exists."""
    import os

    os.chdir(temp_dir)

    from maverick.config import MaverickConfig, load_config

    config = load_config()
    assert isinstance(config, MaverickConfig)
    # Check defaults
    assert config.model.model_id == "claude-sonnet-4-5-20250929"
    assert config.model.max_tokens == 64000
    assert config.parallel.max_agents == 3
    assert config.verbosity == "warning"


def test_load_project_config(
    clean_env: None, temp_dir: Path, sample_config_yaml: str
) -> None:
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
    assert config.model.model_id == "claude-sonnet-4-5-20250929"


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
    assert config.model.model_id == "claude-sonnet-4-5-20250929"
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
    assert config.model.model_id == "claude-sonnet-4-5-20250929"
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
    assert config.model.model_id == "claude-sonnet-4-5-20250929"


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
        if "notifications" in record.message.lower()
        and "topic" in record.message.lower()
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
        if "notifications" in record.message.lower()
        and "topic" in record.message.lower()
    ]
    assert len(notification_warnings) == 0
