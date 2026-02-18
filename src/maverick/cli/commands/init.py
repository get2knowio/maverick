"""CLI command for maverick init.

This module provides the `maverick init` command for project initialization,
including prerequisite validation, project type detection, and configuration
generation.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import cli_error_handler
from maverick.cli.context import ExitCode, async_command
from maverick.exceptions.init import ConfigExistsError, PrerequisiteError
from maverick.init import (
    InitResult,
    PreflightStatus,
    ProjectType,
    resolve_model_id,
    run_init,
)
from maverick.logging import get_logger

# Exit code for config exists (per CLI contract)
CONFIG_EXISTS_EXIT_CODE = 2


def _format_check_status(
    passed: bool,
    message: str,
    display_name: str | None = None,
) -> str:
    """Format a single check status line.

    Args:
        passed: Whether the check passed.
        message: Message to display.
        display_name: Optional display name (used for consistency).

    Returns:
        Formatted status line.
    """
    symbol = "✓" if passed else "✗"
    return f"  {symbol} {message}"


def _format_preflight_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format preflight check output.

    Args:
        result: Init result containing preflight data.
        verbose: Whether to show verbose output.

    Returns:
        List of formatted output lines.
    """
    lines: list[str] = []
    lines.append("Prerequisites")

    for check in result.preflight.checks:
        if check.status == PreflightStatus.PASS:
            lines.append(f"  ✓ {check.message}")
        elif check.status == PreflightStatus.FAIL:
            lines.append(f"  ✗ {check.message}")
        elif check.status == PreflightStatus.SKIP and verbose:
            lines.append(f"  ○ {check.message}")

    lines.append("")
    return lines


def _format_detection_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format project detection output.

    Args:
        result: Init result containing detection data.
        verbose: Whether to show verbose output.

    Returns:
        List of formatted output lines.
    """
    lines: list[str] = []

    if result.detection is None:
        return lines

    detection = result.detection
    lines.append("Project Detection")
    primary_display = detection.primary_type.value.replace("_", " ").title()
    lines.append(f"  Primary type: {primary_display}")

    if verbose:
        detected_types = ", ".join(
            t.value.replace("_", " ").title() for t in detection.detected_types
        )
        lines.append(f"  Detected types: {detected_types}")

    lines.append(f"  Confidence: {detection.confidence.value}")
    lines.append(f"  Detection method: {detection.detection_method}")
    lines.append("")

    # Findings
    if verbose and detection.findings:
        lines.append("Findings")
        for finding in detection.findings:
            lines.append(f"  • {finding}")
        lines.append("")

    return lines


def _format_git_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format git remote output.

    Args:
        result: Init result containing git info.
        verbose: Whether to show verbose output.

    Returns:
        List of formatted output lines.
    """
    lines: list[str] = []
    git_info = result.git_info

    if git_info.owner and git_info.repo:
        if verbose:
            lines.append("Git Remote")
            lines.append(f"  Owner: {git_info.owner}")
            lines.append(f"  Repo: {git_info.repo}")
            if git_info.remote_url:
                lines.append(f"  Remote: {git_info.remote_url}")
            lines.append("")
    else:
        lines.append(
            "⚠ Warning: No git remote configured. GitHub owner/repo set to null."
        )
        lines.append("")

    return lines


def _format_config_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format generated configuration output.

    Args:
        result: Init result containing config data.
        verbose: Whether to show verbose output.

    Returns:
        List of formatted output lines.
    """
    lines: list[str] = []

    if not verbose:
        return lines

    config = result.config
    lines.append("Generated Configuration")

    if config.validation.format_cmd:
        lines.append(f"  Format: {' '.join(config.validation.format_cmd)}")
    if config.validation.lint_cmd:
        lines.append(f"  Lint: {' '.join(config.validation.lint_cmd)}")
    if config.validation.typecheck_cmd:
        lines.append(f"  Typecheck: {' '.join(config.validation.typecheck_cmd)}")
    if config.validation.test_cmd:
        lines.append(f"  Test: {' '.join(config.validation.test_cmd)}")

    lines.append("")
    return lines


# Type choices from ProjectType enum values
PROJECT_TYPE_CHOICES = [
    "python",
    "nodejs",
    "go",
    "rust",
    "ansible_collection",
    "ansible_playbook",
]


@click.command("init")
@click.option(
    "--type",
    "project_type",
    type=click.Choice(PROJECT_TYPE_CHOICES, case_sensitive=False),
    default=None,
    help="Override project type detection.",
)
@click.option(
    "--model",
    "model_name",
    type=str,
    default=None,
    help="Claude model to use (opus, sonnet, haiku, or full model ID).",
)
@click.option(
    "--no-detect",
    is_flag=True,
    default=False,
    help="Use marker-based heuristics instead of Claude.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing maverick.yaml.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show detailed output.",
)
@click.pass_context
@async_command
async def init(
    ctx: click.Context,
    project_type: str | None,
    model_name: str | None,
    no_detect: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Initialize maverick configuration for the current project.

    Validates prerequisites, detects project type (using Claude by default),
    and generates a maverick.yaml configuration file.

    Examples:

        maverick init

        maverick init --type python

        maverick init --model opus

        maverick init --model sonnet --no-detect --force

        maverick init -v
    """
    _logger = get_logger(__name__)  # noqa: F841 - Reserved for future use

    # Print header
    click.echo("Maverick Init")
    click.echo("=============")
    click.echo("")

    # Convert project_type string to ProjectType enum if provided
    type_override: ProjectType | None = None
    if project_type:
        type_override = ProjectType.from_string(project_type)

    # Resolve model name to full model ID if provided
    model_id: str | None = None
    if model_name:
        try:
            model_id = resolve_model_id(model_name)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(ExitCode.FAILURE) from None

    # Determine if we should use Claude
    use_claude = not no_detect

    with cli_error_handler():
        try:
            # Run init workflow
            result = await run_init(
                project_path=Path.cwd(),
                type_override=type_override,
                use_claude=use_claude,
                force=force,
                verbose=verbose,
                model_id=model_id,
            )

            # Format and display output
            lines: list[str] = []
            lines.extend(_format_preflight_output(result, verbose))
            lines.extend(_format_detection_output(result, verbose))
            lines.extend(_format_git_output(result, verbose))
            lines.extend(_format_config_output(result, verbose))

            # Print all lines
            for line in lines:
                click.echo(line)

            # jj init status (only show if initialized)
            if result.jj_initialized:
                click.echo("✓ Jujutsu colocated repo initialized (.jj/)")

            # Beads init status (only show if initialized)
            if result.beads_initialized:
                click.echo("✓ Beads initialized (.beads/)")

            # Success message
            click.echo(f"✓ Configuration written to {result.config_path}")
            raise SystemExit(ExitCode.SUCCESS)

        except PrerequisiteError as e:
            # Show preflight output with failure
            click.echo("Prerequisites")
            click.echo(f"  ✗ {e.check.display_name}: {e.check.message}")
            click.echo("")
            click.echo(f"Error: {e.message}")
            click.echo("")
            if e.check.remediation:
                click.echo(f"Remediation: {e.check.remediation}")
            raise SystemExit(ExitCode.FAILURE) from None

        except ConfigExistsError as e:
            click.echo(f"Error: {e.config_path} already exists.")
            click.echo("")
            click.echo("Use --force to overwrite the existing configuration.")
            raise SystemExit(CONFIG_EXISTS_EXIT_CODE) from None
