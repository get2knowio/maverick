"""Preflight validation actions for DSL workflows.

This module provides preflight checks to run before workflow execution,
ensuring all required tools and credentials are available.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from maverick.config import MaverickConfig, load_config
from maverick.events import OutputLevel, StepOutput
from maverick.exceptions import ConfigError, MaverickError
from maverick.logging import get_logger

logger = get_logger(__name__)


class PreflightError(MaverickError):
    """Raised when preflight checks fail and fail_on_error is True."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        message = "Preflight checks failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PreflightCheckResult:
    """Result of preflight validation checks.

    Attributes:
        success: True if all preflight checks passed.
        providers_available: True if all configured ACP providers are healthy.
        git_available: True if git is available.
        github_cli_available: True if gh CLI is available and authenticated.
        validation_tools_available: True if all validation tools are installed.
        errors: List of error messages for failed checks.
        warnings: List of warning messages for non-critical issues.
    """

    success: bool
    providers_available: bool = True
    git_available: bool = True
    jj_available: bool = True
    github_cli_available: bool = True
    validation_tools_available: bool = True
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DSL serialization."""
        return {
            "success": self.success,
            "providers_available": self.providers_available,
            "git_available": self.git_available,
            "jj_available": self.jj_available,
            "github_cli_available": self.github_cli_available,
            "validation_tools_available": self.validation_tools_available,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


async def _emit_check(
    event_callback: Any | None,
    name: str,
    passed: bool,
    detail: str = "",
) -> None:
    """Emit a StepOutput event for a preflight check result.

    Args:
        event_callback: Optional callback to emit events.
        name: Display name of the check.
        passed: Whether the check passed.
        detail: Optional detail message.
    """
    if event_callback is None:
        return
    icon = "\u2713" if passed else "\u2717"
    level: OutputLevel = "success" if passed else "error"
    message = f" {icon} {name}"
    if detail:
        message = f"{message} \u2014 {detail}"
    await event_callback(
        StepOutput(
            step_name="preflight",
            message=message,
            level=level,
            source="preflight",
        )
    )


async def run_preflight_checks(
    check_providers: bool = True,
    check_git: bool = True,
    check_jj: bool = False,
    check_github: bool = True,
    check_bd: bool = False,
    check_validation_tools: bool = True,
    validation_stages: list[str] | None = None,
    fail_on_error: bool = True,
    event_callback: Any | None = None,
    config: MaverickConfig | None = None,
) -> PreflightCheckResult:
    """Run preflight validation checks before workflow execution.

    This action validates that all required tools and credentials are
    available before starting the workflow. It's designed to fail fast
    with clear error messages rather than failing mid-workflow.

    Args:
        check_providers: Whether to validate ACP provider health
            (binary, auth, protocol handshake).
        check_git: Whether to validate git is available.
        check_jj: Whether to validate jj (Jujutsu) CLI is available.
        check_github: Whether to validate GitHub CLI is authenticated.
        check_bd: Whether to validate the ``bd`` CLI is available.
        check_validation_tools: Whether to validate validation tools are installed.
        validation_stages: List of validation stages to check tools for.
            Defaults to ["format", "lint", "typecheck", "test"].
        fail_on_error: If True (default), raise PreflightError when checks fail
            instead of returning a result with success=False. This causes the
            workflow to stop immediately with a clear error message.

    Returns:
        PreflightCheckResult with success status and any errors/warnings.

    Raises:
        PreflightError: If fail_on_error is True and any preflight checks fail.

    Example:
        # Fail workflow on preflight errors (default)
        result = await run_preflight_checks(check_providers=True)
        # Workflow stops here if provider check fails

        # Return result without failing (for conditional logic)
        result = await run_preflight_checks(check_providers=True, fail_on_error=False)
        if not result.success:
            # Handle failure gracefully
            ...
    """
    if validation_stages is None:
        validation_stages = ["format", "lint", "typecheck", "test"]

    errors: list[str] = []
    warnings: list[str] = []
    providers_available = True
    git_available = True
    jj_available = True
    github_cli_available = True
    validation_tools_available = True

    # Load config for validation commands (use provided config if available)
    if config is None:
        try:
            config = load_config()
        except (ConfigError, ValidationError, FileNotFoundError, OSError) as e:
            logger.warning(
                "Failed to load config, using defaults",
                error=str(e),
                error_type=type(e).__name__,
            )
            config = MaverickConfig()

    # Check ACP providers
    if check_providers:
        from maverick.executor.provider_registry import AgentProviderRegistry
        from maverick.runners.provider_health import AcpProviderHealthCheck

        logger.info("Checking ACP provider health...")
        registry = AgentProviderRegistry.from_config(config.agent_providers)

        # Collect all model IDs per provider from maverick.yaml.
        # For the default provider: global model + all per-agent overrides.
        # For all providers: their own default_model.
        default_provider_name: str | None = None
        for name, pcfg in registry.items():
            if pcfg.default:
                default_provider_name = name
                break
        # Fall back to first provider if none marked default
        if default_provider_name is None and registry.items():
            default_provider_name = next(iter(registry.items()))[0]

        provider_models: dict[str, set[str]] = {}
        for name, pcfg in registry.items():
            models_set: set[str] = set()
            if pcfg.default_model:
                models_set.add(pcfg.default_model)
            provider_models[name] = models_set

        # Global model.model_id → default provider (only if explicitly set)
        # When model_id is the Pydantic default (e.g. claude-sonnet-4-5-*),
        # skip validation — non-Claude providers use their own model aliases.
        model_id_explicit = "model_id" in config.model.model_fields_set
        if default_provider_name and config.model.model_id and model_id_explicit:
            provider_models.setdefault(default_provider_name, set()).add(
                config.model.model_id,
            )

        # Per-agent model_id overrides → default provider
        # (agents don't specify which provider they use)
        if default_provider_name:
            for agent_cfg in config.agents.values():
                if agent_cfg.model_id:
                    provider_models.setdefault(
                        default_provider_name,
                        set(),
                    ).add(agent_cfg.model_id)

        health_checks = [
            AcpProviderHealthCheck(
                provider_name=name,
                provider_config=provider_cfg,
                models_to_validate=frozenset(
                    provider_models.get(name, set()),
                ),
            )
            for name, provider_cfg in registry.items()
        ]

        results = await asyncio.gather(
            *(hc.validate() for hc in health_checks),
            return_exceptions=True,
        )

        for hc, result in zip(health_checks, results, strict=True):
            if isinstance(result, BaseException):
                providers_available = False
                err_msg = f"Provider '{hc.provider_name}' health check error: {result}"
                errors.append(err_msg)
                await _emit_check(
                    event_callback,
                    f"ACP:{hc.provider_name}",
                    False,
                    str(result),
                )
            elif not result.success:
                providers_available = False
                errors.extend(result.errors)
                err_detail = (
                    result.errors[0] if result.errors else "health check failed"
                )
                await _emit_check(
                    event_callback,
                    f"ACP:{hc.provider_name}",
                    False,
                    err_detail,
                )
            else:
                logger.info(
                    "ACP provider healthy",
                    provider=hc.provider_name,
                )
                await _emit_check(
                    event_callback,
                    f"ACP:{hc.provider_name}",
                    True,
                    "healthy",
                )

    # Check git
    if check_git:
        logger.info("Checking git availability...")
        import shutil

        if shutil.which("git") is None:
            git_available = False
            errors.append("Git is not installed or not on PATH")
            logger.debug("Git not found")
            await _emit_check(event_callback, "Git", False, "not installed")
        else:
            logger.info("Git is available")
            await _emit_check(event_callback, "Git", True, "installed")
            # Also check git identity is configured (required for commits)
            try:
                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        "git",
                        "config",
                        "user.name",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    ),
                    timeout=5,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode != 0 or not stdout.strip():
                    git_available = False
                    errors.append(
                        "Git user.name is not configured. "
                        "Run: git config --global user.name 'Your Name'"
                    )
                    logger.debug("Git user.name not configured")
                    await _emit_check(
                        event_callback,
                        "Git user.name",
                        False,
                        "not configured",
                    )
                else:
                    await _emit_check(event_callback, "Git user.name", True)

                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        "git",
                        "config",
                        "user.email",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    ),
                    timeout=5,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode != 0 or not stdout.strip():
                    git_available = False
                    errors.append(
                        "Git user.email is not configured. "
                        "Run: git config --global user.email 'you@example.com'"
                    )
                    logger.debug("Git user.email not configured")
                    await _emit_check(
                        event_callback,
                        "Git user.email",
                        False,
                        "not configured",
                    )
                else:
                    await _emit_check(event_callback, "Git user.email", True)

                if git_available:
                    logger.info("Git identity is configured")
            except TimeoutError:
                warnings.append("Git identity check timed out")
                logger.warning("Git identity check timed out")
            except OSError as e:
                warnings.append(f"Git identity check failed: {e}")
                logger.warning("Git identity check failed", error=str(e))

    # Check jj (Jujutsu) CLI
    if check_jj:
        import shutil as _shutil_jj

        logger.info("Checking jj CLI availability...")
        if _shutil_jj.which("jj") is None:
            jj_available = False
            errors.append(
                "jj (Jujutsu) is not installed or not on PATH. "
                "Install from: https://martinvonz.github.io/jj/latest/install-and-setup/"
            )
            logger.debug("jj CLI not found")
            await _emit_check(event_callback, "jj CLI", False, "not installed")
        else:
            logger.info("jj CLI is available")
            await _emit_check(event_callback, "jj CLI", True, "installed")

    # Check GitHub CLI
    if check_github:
        logger.info("Checking GitHub CLI...")
        import shutil

        if shutil.which("gh") is None:
            github_cli_available = False
            warnings.append(
                "GitHub CLI (gh) is not installed. "
                "PR creation will not be available. "
                "Install from: https://cli.github.com/"
            )
            logger.warning("GitHub CLI not found")
            await _emit_check(event_callback, "GitHub CLI (gh)", False, "not installed")
        else:
            # Check if authenticated using async subprocess
            try:
                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        "gh",
                        "auth",
                        "status",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    ),
                    timeout=10,
                )
                await proc.communicate()
                if proc.returncode != 0:
                    github_cli_available = False
                    warnings.append(
                        "GitHub CLI is not authenticated. "
                        "Run 'gh auth login' to authenticate."
                    )
                    logger.warning("GitHub CLI not authenticated")
                    await _emit_check(
                        event_callback,
                        "GitHub CLI (gh)",
                        False,
                        "not authenticated",
                    )
                else:
                    logger.info("GitHub CLI is available and authenticated")
                    await _emit_check(
                        event_callback,
                        "GitHub CLI (gh)",
                        True,
                        "authenticated",
                    )
            except TimeoutError:
                warnings.append("GitHub CLI auth check timed out")
                logger.warning("GitHub CLI auth check timed out")
            except OSError as e:
                warnings.append(f"GitHub CLI auth check failed: {e}")
                logger.warning(
                    "GitHub CLI auth check failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    # Check bd CLI
    if check_bd:
        import shutil as _shutil_bd

        logger.info("Checking bd CLI availability...")
        if _shutil_bd.which("bd") is None:
            errors.append(
                "bd CLI is not installed or not on PATH. "
                "Run 'maverick init' to initialise the beads tracker."
            )
            logger.debug("bd CLI not found")
            await _emit_check(event_callback, "bd CLI", False, "not installed")
        else:
            logger.info("bd CLI is available")
            await _emit_check(event_callback, "bd CLI", True, "installed")

    # Check validation tools (from maverick.yaml config)
    if check_validation_tools:
        import shutil as _shutil

        logger.info("Checking validation tools...")
        validation_config = config.validation

        # Build list of (display_name, command_list) from config
        tools_to_check: list[tuple[str, list[str]]] = []
        if validation_config.sync_cmd:
            tools_to_check.append(("sync", validation_config.sync_cmd))
        stage_to_cmd = {
            "format": validation_config.format_cmd,
            "lint": validation_config.lint_cmd,
            "typecheck": validation_config.typecheck_cmd,
            "test": validation_config.test_cmd,
        }
        for stage_name in validation_stages:
            cmd = stage_to_cmd.get(stage_name)
            if cmd:
                tools_to_check.append((stage_name, cmd))

        # Check each tool via shutil.which on the first command
        for stage_name, cmd in tools_to_check:
            tool_name = cmd[0]
            tool_path = _shutil.which(tool_name)
            cmd_display = " ".join(cmd[:2])
            if tool_path is None:
                validation_tools_available = False
                errors.append(
                    f"Tool '{tool_name}' (stage '{stage_name}') not found on PATH"
                )
                logger.debug(
                    "Validation tool check failed",
                    tool=tool_name,
                    stage=stage_name,
                )
                await _emit_check(
                    event_callback,
                    f"{stage_name} ({cmd_display})",
                    False,
                    "not found",
                )
            else:
                logger.debug(
                    "Tool found",
                    tool=tool_name,
                    path=tool_path,
                    stage=stage_name,
                )
                await _emit_check(
                    event_callback,
                    f"{stage_name} ({cmd_display})",
                    True,
                )

        # Check custom tools from preflight config
        preflight_config = config.preflight
        for custom in preflight_config.custom_tools:
            tool_path = _shutil.which(custom.command)
            if tool_path is None:
                msg = f"Custom tool '{custom.name}' ({custom.command}) not found"
                if custom.hint:
                    msg = f"{msg}. {custom.hint}"
                if custom.required:
                    errors.append(msg)
                else:
                    warnings.append(msg)
                logger.warning(
                    "Custom tool not found",
                    name=custom.name,
                    command=custom.command,
                    required=custom.required,
                )
                await _emit_check(
                    event_callback,
                    custom.name,
                    False,
                    "not found",
                )
            else:
                logger.debug(
                    "Custom tool found",
                    name=custom.name,
                    path=tool_path,
                )
                await _emit_check(
                    event_callback,
                    custom.name,
                    True,
                )

    # Determine overall success
    # Fail on errors, but not on warnings
    success = len(errors) == 0

    if success:
        logger.info("All preflight checks passed")
    else:
        logger.debug(
            "Preflight checks failed",
            error_count=len(errors),
            errors=errors,
        )
        # Fail immediately if fail_on_error is True
        logger.debug(
            "Preflight fail_on_error check",
            fail_on_error=fail_on_error,
            will_raise=fail_on_error,
        )
        if fail_on_error:
            logger.info("Raising PreflightError to stop workflow")
            raise PreflightError(errors)

    return PreflightCheckResult(
        success=success,
        providers_available=providers_available,
        git_available=git_available,
        jj_available=jj_available,
        github_cli_available=github_cli_available,
        validation_tools_available=validation_tools_available,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
