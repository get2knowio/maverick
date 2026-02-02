"""Preflight validation actions for DSL workflows.

This module provides preflight checks to run before workflow execution,
ensuring all required tools and credentials are available.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from maverick.config import MaverickConfig, load_config
from maverick.exceptions import ConfigError, MaverickError
from maverick.logging import get_logger
from maverick.runners.models import ValidationStage
from maverick.runners.preflight import AnthropicAPIValidator
from maverick.runners.validation import ValidationRunner

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
        api_available: True if Anthropic API is accessible.
        git_available: True if git is available.
        github_cli_available: True if gh CLI is available and authenticated.
        validation_tools_available: True if all validation tools are installed.
        errors: List of error messages for failed checks.
        warnings: List of warning messages for non-critical issues.
    """

    success: bool
    api_available: bool = True
    git_available: bool = True
    github_cli_available: bool = True
    validation_tools_available: bool = True
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DSL serialization."""
        return {
            "success": self.success,
            "api_available": self.api_available,
            "git_available": self.git_available,
            "github_cli_available": self.github_cli_available,
            "validation_tools_available": self.validation_tools_available,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


async def run_preflight_checks(
    check_api: bool = True,
    check_git: bool = True,
    check_github: bool = True,
    check_validation_tools: bool = True,
    validation_stages: list[str] | None = None,
    fail_on_error: bool = True,
) -> PreflightCheckResult:
    """Run preflight validation checks before workflow execution.

    This action validates that all required tools and credentials are
    available before starting the workflow. It's designed to fail fast
    with clear error messages rather than failing mid-workflow.

    Args:
        check_api: Whether to validate Anthropic API access.
        check_git: Whether to validate git is available.
        check_github: Whether to validate GitHub CLI is authenticated.
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
        result = await run_preflight_checks(check_api=True)
        # Workflow stops here if API check fails

        # Return result without failing (for conditional logic)
        result = await run_preflight_checks(check_api=True, fail_on_error=False)
        if not result.success:
            # Handle failure gracefully
            ...
    """
    import os

    if validation_stages is None:
        validation_stages = ["format", "lint", "typecheck", "test"]

    # Debug: log env variable status
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    logger.debug(
        "Preflight environment check",
        anthropic_key_set=bool(anthropic_key),
        anthropic_key_len=len(anthropic_key) if anthropic_key else 0,
        oauth_token_set=bool(oauth_token),
        fail_on_error_param=fail_on_error,
    )

    errors: list[str] = []
    warnings: list[str] = []
    api_available = True
    git_available = True
    github_cli_available = True
    validation_tools_available = True

    # Load config for validation commands
    try:
        config = load_config()
    except (ConfigError, ValidationError, FileNotFoundError, OSError) as e:
        logger.warning(
            "Failed to load config, using defaults",
            error=str(e),
            error_type=type(e).__name__,
        )
        config = MaverickConfig()

    # Check Anthropic API
    if check_api:
        logger.info("Checking Anthropic API access...")
        api_validator = AnthropicAPIValidator(validate_access=False)
        api_result = await api_validator.validate()
        if not api_result.success:
            api_available = False
            errors.extend(api_result.errors)
            logger.error("Anthropic API check failed", errors=api_result.errors)
        else:
            logger.info("Anthropic API credentials found")

    # Check git
    if check_git:
        logger.info("Checking git availability...")
        import shutil

        if shutil.which("git") is None:
            git_available = False
            errors.append("Git is not installed or not on PATH")
            logger.error("Git not found")
        else:
            logger.info("Git is available")
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
                    logger.error("Git user.name not configured")

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
                    logger.error("Git user.email not configured")

                if git_available:
                    logger.info("Git identity is configured")
            except TimeoutError:
                warnings.append("Git identity check timed out")
                logger.warning("Git identity check timed out")
            except OSError as e:
                warnings.append(f"Git identity check failed: {e}")
                logger.warning("Git identity check failed", error=str(e))

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
                else:
                    logger.info("GitHub CLI is available and authenticated")
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

    # Check validation tools
    if check_validation_tools:
        logger.info("Checking validation tools...")
        validation_config = config.validation
        timeout = validation_config.timeout_seconds

        # Map stage names to commands
        stage_to_cmd = {
            "format": validation_config.format_cmd,
            "lint": validation_config.lint_cmd,
            "typecheck": validation_config.typecheck_cmd,
            "test": validation_config.test_cmd,
        }

        # Build ValidationStage objects for requested stages
        stages_to_check: list[ValidationStage] = []
        for stage_name in validation_stages:
            cmd = stage_to_cmd.get(stage_name)
            if cmd:
                stages_to_check.append(
                    ValidationStage(
                        name=stage_name,
                        command=tuple(cmd),
                        fixable=False,
                        fix_command=None,
                        timeout_seconds=timeout,
                    )
                )

        if stages_to_check:
            # Use ValidationRunner's validate method to check tools
            cwd = validation_config.project_root or Path.cwd()
            runner = ValidationRunner(stages=stages_to_check, cwd=cwd)
            tool_result = await runner.validate()

            if not tool_result.success:
                validation_tools_available = False
                for error in tool_result.errors:
                    errors.append(error)
                    logger.error("Validation tool check failed", error=error)
            else:
                logger.info(
                    "All validation tools available",
                    stages=validation_stages,
                )

            # Add warnings
            warnings.extend(tool_result.warnings)

    # Determine overall success
    # Fail on errors, but not on warnings
    success = len(errors) == 0

    if success:
        logger.info("All preflight checks passed")
    else:
        logger.error(
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
        api_available=api_available,
        git_available=git_available,
        github_cli_available=github_cli_available,
        validation_tools_available=validation_tools_available,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
