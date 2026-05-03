"""``maverick init`` command — project initialization.

Validates prerequisites, detects project type from marker files, queries
OpenCode's ``GET /provider`` endpoint to discover authenticated
providers, and writes a complete ``maverick.yaml`` (project metadata +
``agent_providers`` + ``provider_tiers`` + ``validation`` defaults).

The legacy ``--providers`` / ``--skip-providers`` / ``--models`` flags
were deleted in the OpenCode-substrate cleanup. The flags filtered which
ACP bridges to probe via PATH, which made sense when each "provider"
was a stdio binary like ``claude-agent-acp``. Under the OpenCode HTTP
runtime, providers are connected at the OpenCode layer (via
``opencode auth login <provider>``) and discovered automatically — no
filter is meaningful.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import cli_error_handler
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.exceptions.init import PrerequisiteError
from maverick.init import (
    InitResult,
    OpenCodeDiscoveryResult,
    PreflightStatus,
    ProjectType,
    run_init,
)


def _format_preflight_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format preflight check output."""
    lines: list[str] = ["[bold]Prerequisites[/]"]

    for check in result.preflight.checks:
        if check.status == PreflightStatus.PASS:
            lines.append(f"  [green]✓[/] {check.message}")
        elif check.status == PreflightStatus.FAIL:
            lines.append(f"  [red]✗[/] {check.message}")
        elif check.status == PreflightStatus.SKIP and verbose:
            lines.append(f"  [dim]○[/] {check.message}")

    lines.append("")
    return lines


def _format_detection_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format project detection output."""
    lines: list[str] = []

    if result.detection is None:
        return lines

    detection = result.detection
    primary_display = detection.primary_type.value.replace("_", " ").title()
    lines.append("[bold]Project Detection[/]")
    lines.append(f"  Primary type: [cyan]{primary_display}[/]")

    if verbose:
        detected_types = ", ".join(
            t.value.replace("_", " ").title() for t in detection.detected_types
        )
        lines.append(f"  Detected types: {detected_types}")

    lines.append(f"  Confidence: {detection.confidence.value}")
    lines.append(f"  Detection method: {detection.detection_method}")
    lines.append("")

    if verbose and detection.findings:
        lines.append("[bold]Findings[/]")
        for finding in detection.findings:
            lines.append(f"  [dim]•[/] {finding}")
        lines.append("")

    return lines


def _format_provider_output(
    discovery: OpenCodeDiscoveryResult | None,
) -> list[str]:
    """Format OpenCode-connected provider output."""
    if discovery is None:
        return [
            "[bold]OpenCode Providers[/]",
            "  [yellow]Warning:[/yellow] OpenCode discovery failed; "
            "agent_providers section will be empty.",
            "",
        ]

    lines: list[str] = ["[bold]OpenCode Providers[/]"]

    if not discovery.providers:
        lines.append("  [yellow]Warning:[/yellow] No providers connected.")
        lines.append(
            "  Run [bold]opencode auth login <provider>[/] (e.g. "
            "github-copilot, openai, openrouter)."
        )
        lines.append("")
        return lines

    for prov in discovery.providers:
        suffix = ""
        if prov.provider_id == discovery.default_provider_id:
            suffix = " [dim](default)[/]"
        model_blurb = ""
        if prov.default_model_id:
            model_blurb = f" — default model: [dim]{prov.default_model_id}[/]"
        lines.append(
            f"  [green]✓[/] {prov.display_name} ({prov.provider_id}){suffix}{model_blurb}"
        )

    lines.append("")
    return lines


def _format_git_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format git remote output."""
    lines: list[str] = []
    git_info = result.git_info

    if git_info.owner and git_info.repo:
        if verbose:
            lines.append("[bold]Git Remote[/]")
            lines.append(f"  Owner: {git_info.owner}")
            lines.append(f"  Repo: {git_info.repo}")
            if git_info.remote_url:
                lines.append(f"  Remote: {git_info.remote_url}")
            lines.append("")
    else:
        lines.append(
            "[yellow]Warning:[/yellow] No git remote configured. GitHub owner/repo set to null."
        )
        lines.append("")

    return lines


def _format_config_output(
    result: InitResult,
    verbose: bool = False,
) -> list[str]:
    """Format generated configuration output."""
    lines: list[str] = []

    if not verbose:
        return lines

    config = result.config
    if config is None:
        # Idempotent re-init path: no fresh config was generated. Nothing
        # to display in this section.
        return lines
    lines.append("[bold]Generated Configuration[/]")

    if config.validation.format_cmd:
        lines.append(f"  Format: [dim]{' '.join(config.validation.format_cmd)}[/]")
    if config.validation.lint_cmd:
        lines.append(f"  Lint: [dim]{' '.join(config.validation.lint_cmd)}[/]")
    if config.validation.typecheck_cmd:
        lines.append(f"  Typecheck: [dim]{' '.join(config.validation.typecheck_cmd)}[/]")
    if config.validation.test_cmd:
        lines.append(f"  Test: [dim]{' '.join(config.validation.test_cmd)}[/]")

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
    force: bool,
    verbose: bool,
) -> None:
    """Initialize maverick configuration for the current project.

    Detects project type from marker files, probes OpenCode's connected
    providers, and writes a maverick.yaml with provider_tiers cascade
    pre-populated.

    Examples:

        maverick init

        maverick init --type python

        maverick init --force -v
    """
    console.print("[bold cyan]Maverick Init[/]")
    console.print()

    type_override: ProjectType | None = None
    if project_type:
        type_override = ProjectType.from_string(project_type)

    with cli_error_handler():
        try:
            result = await run_init(
                project_path=Path.cwd(),
                type_override=type_override,
                force=force,
                verbose=verbose,
            )

            lines: list[str] = []
            lines.extend(_format_preflight_output(result, verbose))
            lines.extend(_format_detection_output(result, verbose))
            lines.extend(_format_provider_output(result.provider_discovery))
            lines.extend(_format_git_output(result, verbose))
            lines.extend(_format_config_output(result, verbose))

            for line in lines:
                console.print(line)

            if result.beads_initialized:
                console.print("[green]✓[/] Beads initialized (.beads/)")

            # Idempotent re-init path: maverick.yaml already existed and
            # ``--force`` was not passed. (FUTURE.md §4.3)
            if result.config_existed:
                console.print()
                console.print(
                    f"[green]✓[/] Already initialized at [bold]{result.config_path}[/] — "
                    "beads + runway re-checked, configuration unchanged."
                )
                console.print()
                console.print("[dim]Use [bold]--force[/bold] to regenerate the configuration.[/]")
                raise SystemExit(ExitCode.SUCCESS)

            console.print()
            console.print(f"[green]✓[/] Configuration written to [bold]{result.config_path}[/]")

            if (
                result.runway_initialized
                and result.provider_discovery
                and result.provider_discovery.providers
            ):
                console.print()
                console.print(
                    "[dim]Tip: Run 'maverick runway seed' to pre-populate the runway\n"
                    "     knowledge store with AI-generated codebase insights.[/]"
                )

            raise SystemExit(ExitCode.SUCCESS)

        except PrerequisiteError as e:
            err_console.print("[bold]Prerequisites[/]")
            err_console.print(f"  [red]✗[/] {e.check.display_name}: {e.check.message}")
            err_console.print()
            err_console.print(f"[red]Error:[/red] {e.message}")
            if e.check.remediation:
                err_console.print()
                err_console.print(f"[yellow]Remediation:[/yellow] {e.check.remediation}")
            raise SystemExit(ExitCode.FAILURE) from None
