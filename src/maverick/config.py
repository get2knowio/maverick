from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from maverick.exceptions import ConfigError

logger = logging.getLogger(__name__)


class GitHubConfig(BaseModel):
    """Settings for GitHub integration."""

    owner: str | None = None
    repo: str | None = None
    default_branch: str = "main"


class NotificationConfig(BaseModel):
    """Settings for ntfy-based push notifications."""

    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str | None = None


class ModelConfig(BaseModel):
    """Settings for Claude model selection."""

    model_id: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=8192, gt=0, le=200000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class ParallelConfig(BaseModel):
    """Settings for concurrency limits."""

    max_agents: int = Field(default=3, gt=0, le=10)
    max_tasks: int = Field(default=5, gt=0, le=20)


class AgentConfig(BaseModel):
    """Flat key-value configuration for agent-specific overrides."""

    model_id: str | None = None
    max_tokens: int | None = Field(default=None, gt=0, le=200000)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)


class YamlConfigSource(PydanticBaseSettingsSource):
    """Custom settings source that loads from YAML files."""

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        yaml_file: Path | None = None,
    ):
        super().__init__(settings_cls)
        self.yaml_file = yaml_file
        self._config_data: dict[str, Any] = {}
        if yaml_file and yaml_file.exists():
            try:
                with open(yaml_file) as f:
                    loaded = yaml.safe_load(f)
                    if loaded is None:
                        logger.warning(
                            f"Config file {yaml_file} is empty, using defaults."
                        )
                    elif loaded:
                        self._config_data = loaded
            except yaml.YAMLError as e:
                raise ConfigError(
                    message=f"Invalid YAML in {yaml_file}: {e}",
                    field=None,
                    value=None,
                ) from e

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        """Get value for a specific field from the YAML config."""
        if field_name in self._config_data:
            return self._config_data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Return the complete config data."""
        return self._config_data


class MaverickConfig(BaseSettings):
    """Root configuration object containing all Maverick settings."""

    model_config = SettingsConfigDict(
        env_prefix="MAVERICK_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    github: GitHubConfig = Field(default_factory=GitHubConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    verbosity: Literal["error", "warning", "info", "debug"] = "warning"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize the order of settings sources.

        Priority (highest to lowest):
        1. Environment variables
        2. Project YAML config
        3. User YAML config
        4. Init settings (defaults)

        Note: pydantic-settings reads sources from right to left,
        so highest priority sources come last in the tuple.
        """
        # Get user and project config paths
        user_config_path = get_user_config_path()
        project_config_path = Path.cwd() / "maverick.yaml"

        # Return sources from highest to lowest priority
        # (later sources override earlier ones)
        return (
            env_settings,  # Environment variables (highest priority)
            YamlConfigSource(settings_cls, project_config_path),  # Project config
            YamlConfigSource(settings_cls, user_config_path),  # User config
        )


def get_user_config_path() -> Path:
    """Get the path to the user configuration file.

    Returns:
        Path to ~/.config/maverick/config.yaml
    """
    return Path.home() / ".config" / "maverick" / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary to merge into base

    Returns:
        Merged dictionary where nested dicts are merged recursively
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> MaverickConfig:
    """Load configuration with hierarchy: defaults -> user -> project -> env.

    The configuration is loaded in the following order (lowest to highest priority):
    1. Built-in defaults (Pydantic model defaults)
    2. User config (~/.config/maverick/config.yaml)
    3. Project config (./maverick.yaml or provided config_path)
    4. Environment variables (MAVERICK_*)

    Args:
        config_path: Optional path to project config file. Defaults to ./maverick.yaml

    Returns:
        MaverickConfig instance with merged configuration

    Raises:
        ConfigError: If configuration is invalid
    """
    if config_path is None:
        config_path = Path.cwd() / "maverick.yaml"

    # Log if no project config found
    if not config_path.exists():
        logger.info("No project configuration found, using defaults.")

    # Note: The actual config loading hierarchy is handled by
    # settings_customise_sources() in MaverickConfig
    try:
        return MaverickConfig()
    except ValidationError as e:
        # Extract first error for ConfigError
        first_error = e.errors()[0]
        field = ".".join(str(loc) for loc in first_error["loc"])
        raise ConfigError(
            message=f"Invalid configuration: {first_error['msg']}",
            field=field,
            value=first_error.get("input"),
        ) from e
