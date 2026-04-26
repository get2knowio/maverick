from __future__ import annotations

import contextvars
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from maverick.constants import (
    DEFAULT_MODEL as MAVERICK_DEFAULT_MODEL,
)
from maverick.constants import (
    MAX_OUTPUT_TOKENS,
)
from maverick.exceptions import ConfigError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig
    from maverick.prompts.config import PromptOverrideConfig

__all__ = [
    "MaverickConfig",
    "GitHubConfig",
    "NotificationConfig",
    "ValidationConfig",
    "PreflightValidationConfig",
    "CustomToolConfig",
    "ModelConfig",
    "ParallelConfig",
    "TuiMetricsConfig",
    "SessionLogConfig",
    "WorkspaceConfig",
    "AgentConfig",
    "RunwayConfig",
    "RunwayConsolidationConfig",
    "RunwayRetrievalConfig",
    "PermissionMode",
    "AgentProviderConfig",
    "load_config",
    "get_user_config_path",
]

logger = get_logger(__name__)

_project_config_path_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "_project_config_path", default=None
)


class PermissionMode(str, Enum):
    """Permission handling strategy for ACP agent tool calls."""

    AUTO_APPROVE = "auto_approve"
    DENY_DANGEROUS = "deny_dangerous"
    INTERACTIVE = "interactive"


class AgentProviderConfig(BaseModel, frozen=True):
    """Configuration for a single ACP agent provider.

    Attributes:
        command: Subprocess command and arguments to spawn the agent.
        env: Environment variable overrides for the subprocess.
        permission_mode: How to handle agent permission requests.
        default: Whether this is the default provider.
    """

    command: list[str] | None = Field(
        default=None,
        description=(
            "Spawn command and args. Optional for built-in providers "
            "(claude, copilot) — resolved automatically by the registry."
        ),
    )
    env: dict[str, str] = Field(default_factory=dict, description="Environment overrides")
    permission_mode: PermissionMode = Field(
        default=PermissionMode.AUTO_APPROVE,
        description="Permission handling strategy",
    )
    default: bool = Field(default=False, description="Is this the default provider?")
    default_model: str | None = Field(
        default=None,
        description="Default model for this provider (lowest precedence layer).",
    )


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

    @model_validator(mode="after")
    def check_topic_when_enabled(self) -> Self:
        if self.enabled and self.topic is None:
            logger.warning(
                "Notifications enabled but no topic specified. Notifications will not be sent."
            )
        return self


class ValidationConfig(BaseModel):
    """Settings for validation commands.

    Attributes:
        sync_cmd: Command to sync/install dependencies (auto-detected if omitted).
        format_cmd: Command to run for formatting (default: ruff format .)
        lint_cmd: Command to run for linting (default: ruff check --fix .)
        typecheck_cmd: Command to run for type checking (default: mypy .)
        test_cmd: Command to run for tests (default: pytest -x --tb=short)
        timeout_seconds: Maximum time per validation command (default: 300s)
        max_errors: Maximum errors to return from parse (default: 50)
        project_root: Project root directory for running commands (default: cwd)
    """

    sync_cmd: list[str] | None = Field(
        default=None,
        description="Command to sync/install dependencies (auto-detected if omitted)",
    )
    format_cmd: list[str] = Field(default_factory=lambda: ["ruff", "format", "."])
    lint_cmd: list[str] = Field(default_factory=lambda: ["ruff", "check", "--fix", "."])
    typecheck_cmd: list[str] = Field(default_factory=lambda: ["mypy", "."])
    test_cmd: list[str] = Field(default_factory=lambda: ["pytest", "-x", "--tb=short"])
    timeout_seconds: int = Field(default=300, ge=30, le=600)
    max_errors: int = Field(default=50, ge=1, le=500)
    project_root: Path | None = None

    @field_validator("project_root")
    @classmethod
    def check_project_root_exists(cls, v: Path | None) -> Path | None:
        """Warn if project_root path doesn't exist."""
        if v is not None and not v.exists():
            logger.warning(
                f"Configured project_root does not exist: {v}. Validation commands may fail."
            )
        return v


class ModelConfig(BaseModel):
    """Settings for Claude model selection.

    Attributes:
        model_id: Claude model identifier.
        max_tokens: Maximum OUTPUT tokens per response (not context window).
            Defaults to 64000 (maximum for all Claude 4.5 variants).
            Context window (input): 200K tokens (fixed by model).
            Max output (configurable): up to 64K tokens.
            Model limits (all Claude 4.5 variants):
            - {CLAUDE_SONNET_LATEST}: 64K output, 200K context (default)
            - {CLAUDE_OPUS_LATEST}: 64K output, 200K context
            - {CLAUDE_HAIKU_LATEST}: 64K output, 200K context
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
    """

    model_id: str = MAVERICK_DEFAULT_MODEL
    max_tokens: int = Field(default=MAX_OUTPUT_TOKENS, gt=0, le=200000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class ImplementerTierConfig(BaseModel):
    """Per-tier override for the implementer step.

    A subset of ``StepConfig`` fields that are meaningful per-tier.
    Each tier maps a bead's ``complexity`` (set by the decomposer at
    refuel time) to a specific provider/model so trivial work doesn't
    pay frontier prices and complex work doesn't suffer weak models.

    Tier configs override the implementer's top-level config when
    selected; any field left ``None`` falls back to the implementer's
    base ``StepConfig``.
    """

    provider: str | None = None
    model_id: str | None = None
    timeout: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0, le=200000)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)


class ImplementerTiersConfig(BaseModel):
    """Tier routing for the implementer step (FUTURE.md §2.10 Phase 2).

    When set, the fly supervisor spawns one ``ImplementerActor`` per
    defined tier, each with its tier's StepConfig (and therefore its own
    ACP subprocess). Beads are dispatched to the actor matching their
    decomposer-assigned ``complexity``.

    A bead with no complexity (older runs, or decomposer didn't classify)
    routes to ``moderate`` by default.

    On fix-loop overflow at a tier, the supervisor promotes the bead
    one tier upward (where one is defined) and routes the next attempt
    to the higher-tier actor. Recorded as ``fly.complexity_escalated``
    in the runway so classification accuracy can be measured.

    Attributes:
        trivial / simple / moderate / complex: Per-tier overrides.
            Omit a tier to disable it (the supervisor will fall back to
            the next tier up, or to the implementer's base config when
            no tiers above are defined).
        escalation_threshold: Number of fix rounds with findings at the
            current tier before automatically promoting one tier up.
            Default 2. Set to 0 to disable escalation.
    """

    trivial: ImplementerTierConfig | None = None
    simple: ImplementerTierConfig | None = None
    moderate: ImplementerTierConfig | None = None
    complex: ImplementerTierConfig | None = None
    escalation_threshold: int = Field(default=2, ge=0, le=5)


class ParallelConfig(BaseModel):
    """Settings for concurrency limits.

    Attributes:
        max_agents: Reserved global LLM-call concurrency cap. Currently
            advisory only — the per-phase knobs below (``decomposer_pool_size``,
            ``max_briefing_agents``, ``max_parallel_reviewers``) are what the
            workflows actually consult. Will become a global ceiling once the
            per-phase knobs aren't enough.
        max_tasks: Reserved task fan-out cap. Currently advisory.
        decomposer_pool_size: Number of pool workers for the refuel
            detail phase. Default ``3`` matches the legacy hardcoded value
            (``DECOMPOSER_POOL_SIZE = 4`` minus the one primary decomposer).
            Each pool worker holds its own long-lived ``claude-agent-acp``
            subprocess. Lower this on resource-constrained hosts (e.g. dev
            containers): ``decomposer_pool_size: 1`` runs one pool worker
            plus one primary, capping live ACP subprocesses at 2 during the
            detail phase.
        max_briefing_agents: Cap on briefing agents running in parallel
            during refuel and plan generation. Default ``3`` matches the
            current behaviour (navigator/structuralist/recon — or
            scopist/analyst/criteria — all in flight via ``asyncio.gather``).
            Setting to ``1`` runs them sequentially. The contrarian agent
            always runs after the parallel fan-out completes.
        max_parallel_reviewers: Cap on parallel review agents
            (completeness + correctness). Default ``2`` matches the current
            behaviour. Setting to ``1`` runs them sequentially.
    """

    max_agents: int = Field(default=3, gt=0, le=10)
    max_tasks: int = Field(default=5, gt=0, le=20)
    decomposer_pool_size: int = Field(default=3, ge=0, le=10)
    max_briefing_agents: int = Field(default=3, ge=1, le=10)
    max_parallel_reviewers: int = Field(default=2, ge=1, le=4)


class TuiMetricsConfig(BaseModel):
    """Settings for TUI widget performance metrics.

    Attributes:
        enabled: Enable widget metrics collection (opt-in, default: False).
        max_entries: Maximum entries in rolling window per metric type.
    """

    enabled: bool = False
    max_entries: int = Field(default=10000, ge=100, le=1000000)


class CustomToolConfig(BaseModel):
    """Configuration for a custom validation tool.

    Attributes:
        name: Human-readable name for the tool.
        command: Command or path to check (first item for shutil.which).
        required: If True, missing tool is an error; if False, a warning.
        hint: Optional installation hint to show if tool is missing.
    """

    name: str
    command: str
    required: bool = False
    hint: str | None = None


class PreflightValidationConfig(BaseModel):
    """Settings for preflight validation.

    Attributes:
        timeout_per_check: Maximum seconds per validation check (default: 5.0).
        fail_on_warning: Whether warnings should cause preflight to fail
            (default: False).
        custom_tools: List of custom tools to validate.

    Example maverick.yaml:
        preflight:
          timeout_per_check: 10.0
          fail_on_warning: false
          custom_tools:
            - name: "Docker"
              command: "docker"
              required: true
              hint: "Install Docker from https://docker.com/"
            - name: "Custom Script"
              command: "./scripts/setup.sh"
              required: false
    """

    timeout_per_check: float = Field(default=5.0, gt=0.0, le=60.0)
    fail_on_warning: bool = False
    custom_tools: list[CustomToolConfig] = Field(default_factory=list)


class SessionLogConfig(BaseModel):
    """Settings for session journal logging.

    Attributes:
        enabled: Enable session logging by default (default: False).
        output_dir: Default directory for session log files.
        include_agent_text: Include high-volume AgentStreamChunk events
            in the log (default: True).
    """

    enabled: bool = False
    output_dir: Path = Field(default_factory=lambda: Path(".maverick/logs"))
    include_agent_text: bool = True


class WorkspaceConfig(BaseModel):
    """Settings for hidden jj workspaces.

    Attributes:
        root: Base directory for workspace clones.
        setup: Shell command to run after cloning (e.g. ``uv sync``).
        teardown: Shell command to run before removal.
        reuse: If True (default), reuse existing workspace instead of re-cloning.
        env_files: Files to copy from user repo into workspace during bootstrap.
    """

    root: Path = Field(default_factory=lambda: Path.home() / ".maverick" / "workspaces")
    setup: str | None = None
    teardown: str | None = None
    reuse: bool = True
    env_files: list[str] = Field(default_factory=lambda: [".env"])


class RunwayConsolidationConfig(BaseModel):
    """Settings for runway consolidation."""

    auto: bool = True
    max_episodic_age_days: int = Field(default=90, ge=1, le=365)
    max_episodic_records: int = Field(default=500, ge=10, le=10000)


class RunwayRetrievalConfig(BaseModel):
    """Settings for runway retrieval."""

    max_passages: int = Field(default=10, ge=1, le=50)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    max_context_chars: int = Field(default=4000, ge=500, le=20000)


class RunwayConfig(BaseModel):
    """Settings for the runway knowledge store.

    Attributes:
        enabled: Whether runway recording is active.
        path: Path to the runway directory relative to project root.
        consolidation: Consolidation settings.
        retrieval: Retrieval settings.
    """

    enabled: bool = True
    path: str = ".maverick/runway"
    consolidation: RunwayConsolidationConfig = Field(default_factory=RunwayConsolidationConfig)
    retrieval: RunwayRetrievalConfig = Field(default_factory=RunwayRetrievalConfig)


class AgentConfig(BaseModel):
    """Flat key-value configuration for agent-specific overrides."""

    provider: str | None = None
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
                        logger.warning(f"Config file {yaml_file} is empty, using defaults.")
                    elif loaded:
                        self._config_data = loaded
            except yaml.YAMLError as e:
                raise ConfigError(
                    message=f"Invalid YAML in {yaml_file}: {e}",
                    field=None,
                    value=None,
                ) from e

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
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
        defer_build=True,
    )

    github: GitHubConfig = Field(default_factory=GitHubConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    preflight: PreflightValidationConfig = Field(default_factory=PreflightValidationConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)
    tui_metrics: TuiMetricsConfig = Field(default_factory=TuiMetricsConfig)
    session_log: SessionLogConfig = Field(default_factory=SessionLogConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    runway: RunwayConfig = Field(default_factory=RunwayConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    agent_providers: dict[str, AgentProviderConfig] = Field(
        default_factory=dict,
        description="ACP agent provider configurations keyed by provider name.",
    )
    actors: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Actor configurations grouped by workflow (plan/refuel/fly/land).",
    )
    steps: dict[str, StepConfig] = Field(
        default_factory=dict,
        description="Legacy step configuration (superseded by actors:).",
    )
    prompts: dict[str, PromptOverrideConfig] = Field(
        default_factory=dict,
        description="Prompt overrides keyed by step name.",
    )
    project_type: str = Field(
        default="unknown",
        description="Project type (python, rust, go, nodejs, etc.).",
    )
    project_conventions: str = ""

    def __init__(self, **data: Any) -> None:
        _ensure_model_rebuilt()
        super().__init__(**data)

    @field_validator("steps", mode="before")
    @classmethod
    def _coerce_step_configs(cls, v: Any) -> Any:
        """Coerce dict entries to StepConfig via lazy import to avoid circular deps."""
        if not isinstance(v, dict):
            return v
        from maverick.executor.config import StepConfig

        result = {}
        for key, val in v.items():
            if isinstance(val, dict):
                result[key] = StepConfig(**val)
            elif isinstance(val, StepConfig):
                result[key] = val
            else:
                raise ConfigError(
                    message=(
                        f"Invalid step config for '{key}': "
                        f"expected dict or StepConfig, "
                        f"got {type(val).__name__}"
                    ),
                    field=f"steps.{key}",
                    value=val,
                )
        return result

    @field_validator("prompts", mode="before")
    @classmethod
    def _coerce_prompt_overrides(cls, v: Any) -> Any:
        """Coerce dict entries to PromptOverrideConfig."""
        if not isinstance(v, dict):
            return v
        from maverick.prompts.config import PromptOverrideConfig

        result = {}
        for key, val in v.items():
            if isinstance(val, dict):
                result[key] = PromptOverrideConfig(**val)
            elif isinstance(val, PromptOverrideConfig):
                result[key] = val
            else:
                raise ConfigError(
                    message=(
                        f"Invalid prompt config for '{key}': "
                        f"expected dict or PromptOverrideConfig, "
                        f"got {type(val).__name__}"
                    ),
                    field=f"prompts.{key}",
                    value=val,
                )
        return result

    @model_validator(mode="after")
    def _check_prompts_steps_conflict(self) -> Self:
        """Detect conflicts between prompts: and steps: sections."""
        if not self.prompts or not self.steps:
            return self
        for step_name, _override in self.prompts.items():
            if step_name in self.steps:
                step_cfg = self.steps[step_name]
                has_step_suffix = getattr(step_cfg, "prompt_suffix", None) is not None
                has_step_file = getattr(step_cfg, "prompt_file", None) is not None
                if has_step_suffix or has_step_file:
                    raise ConfigError(
                        message=(
                            f"Step '{step_name}' has prompt configuration in both "
                            f"'prompts:' and 'steps:' sections. Use only one."
                        ),
                        field=f"prompts.{step_name}",
                    )
        return self

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
        1. Environment variables (MAVERICK_*)
        2. Project YAML config (./maverick.yaml)
        3. User YAML config (~/.config/maverick/config.yaml)
        4. Init settings (defaults)

        Note: pydantic-settings processes sources from left to right,
        with earlier sources having higher priority. The first source
        to provide a value for a field wins.
        """
        # Get user and project config paths
        user_config_path = get_user_config_path()
        project_config_path = _project_config_path_var.get() or (Path.cwd() / "maverick.yaml")

        # Return sources from highest to lowest priority
        # (earlier sources override later ones)
        return (
            env_settings,  # Environment variables (highest priority)
            # Project config
            YamlConfigSource(settings_cls, project_config_path),
            # User config (lowest)
            YamlConfigSource(settings_cls, user_config_path),
        )


_model_rebuilt = False


def _ensure_model_rebuilt() -> None:
    """Resolve the StepConfig forward reference on first use.

    Called lazily from ``MaverickConfig.__init__`` (not at module scope)
    to avoid circular imports.  By the time any caller instantiates the
    model, all modules have finished loading and the import succeeds.
    """
    global _model_rebuilt  # noqa: PLW0603
    if _model_rebuilt:
        return

    from maverick.executor.config import StepConfig  # noqa: F811
    from maverick.prompts.config import PromptOverrideConfig  # noqa: F811

    MaverickConfig.model_rebuild(
        _types_namespace={
            "StepConfig": StepConfig,
            "PromptOverrideConfig": PromptOverrideConfig,
        },
    )
    _model_rebuilt = True


def get_user_config_path() -> Path:
    """Get the path to the user configuration file.

    Returns:
        Path to ~/.config/maverick/config.yaml
    """
    return Path.home() / ".config" / "maverick" / "config.yaml"


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
    _ensure_model_rebuilt()

    if config_path is None:
        config_path = Path.cwd() / "maverick.yaml"

    # Log if no project config found
    if not config_path.exists():
        logger.info("No project configuration found, using defaults.")

    # Set the context var so settings_customise_sources() picks up the path
    token = _project_config_path_var.set(config_path)
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
    finally:
        _project_config_path_var.reset(token)
