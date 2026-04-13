"""CLI command for maverick init.

This module provides the `maverick init` command for project initialization,
including prerequisite validation, project type detection, and configuration
generation.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import cli_error_handler
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.exceptions.init import ConfigExistsError, PrerequisiteError
from maverick.init import (
    InitResult,
    PreflightStatus,
    ProjectType,
    resolve_model_id,
    run_init,
)
from maverick.init.provider_discovery import ProviderDiscoveryResult
from maverick.logging import get_logger

# Exit code for config exists (per CLI contract)
CONFIG_EXISTS_EXIT_CODE = 2


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
    discovery: ProviderDiscoveryResult | None,
) -> list[str]:
    """Format ACP provider discovery output."""
    if discovery is None:
        return []

    lines: list[str] = ["[bold]ACP Providers[/]"]

    for probe in discovery.providers:
        symbol = "[green]✓[/]" if probe.found else "[red]✗[/]"
        suffix = " [dim](default)[/]" if probe.name == discovery.default_provider else ""
        lines.append(f"  {symbol} {probe.display_name} ({probe.binary}){suffix}")

    if not discovery.found_providers:
        lines.append("  [yellow]⚠[/] No ACP providers found on PATH.")

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
        lines.append("[yellow]⚠[/] No git remote configured. GitHub owner/repo set to null.")
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
    "--skip-providers",
    is_flag=True,
    default=False,
    help="Skip ACP provider discovery.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing maverick.yaml.",
)
@click.option(
    "--providers",
    type=str,
    default=None,
    help="Comma-separated list of ACP providers (e.g., claude,copilot,gemini).",
)
@click.option(
    "--models",
    "model_specs",
    type=str,
    multiple=True,
    help="Provider model specs: provider:model1,model2 (e.g., copilot:gpt-5.3-codex,gpt-5.4).",
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
    skip_providers: bool,
    force: bool,
    providers: str | None,
    model_specs: tuple[str, ...],
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

    console.print("[bold cyan]Maverick Init[/]")
    console.print()

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
            err_console.print(f"[red]Error:[/red] {e}")
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
                skip_providers=skip_providers,
            )

            # Format and display output
            lines: list[str] = []
            lines.extend(_format_preflight_output(result, verbose))
            lines.extend(_format_detection_output(result, verbose))
            lines.extend(_format_provider_output(result.provider_discovery))
            lines.extend(_format_git_output(result, verbose))
            lines.extend(_format_config_output(result, verbose))

            for line in lines:
                console.print(line)

            # Beads init status
            if result.beads_initialized:
                console.print("[green]✓[/] Beads initialized (.beads/)")

            # Write provider MCP config files
            provider_list = (
                [p.strip() for p in providers.split(",") if p.strip()]
                if providers
                else [
                    p.name
                    for p in (
                        result.provider_discovery.found_providers
                        if result.provider_discovery
                        else ()
                    )
                ]
            )
            if provider_list:
                from maverick.init.mcp_config import write_provider_mcp_configs

                mcp_written = write_provider_mcp_configs(provider_list)
                for prov, path in mcp_written.items():
                    console.print(f"[green]✓[/] MCP config written for {prov}: [dim]{path}[/]")

            # Model discovery
            if provider_list:
                from maverick.init.model_discovery import (
                    discover_all_models,
                    parse_model_specs,
                )

                user_specs = parse_model_specs(model_specs) if model_specs else None

                console.print()
                console.print("[bold]Model Discovery[/]")
                discovered = await discover_all_models(provider_list, user_specs)
                for prov, pm in discovered.items():
                    source_label = {
                        "probe": "probed",
                        "user": "specified",
                        "default": "defaults",
                    }.get(pm.source, pm.source)
                    models_str = ", ".join(pm.models[:5])
                    if len(pm.models) > 5:
                        models_str += f" (+{len(pm.models) - 5} more)"
                    console.print(f"  {prov} [dim]({source_label})[/]: {models_str}")

                # Distribute models across actors
                from maverick.init.actor_distribution import distribute_models

                default_prov = (
                    result.provider_discovery.default_provider
                    if result.provider_discovery
                    else provider_list[0]
                    if provider_list
                    else "claude"
                )
                actor_configs = distribute_models(discovered, default_provider=default_prov)

                console.print()
                console.print("[bold]Actor Assignment[/]")
                for workflow, actors in actor_configs.items():
                    for actor_name, ac in actors.items():
                        console.print(
                            f"  {workflow}.{actor_name}: [cyan]{ac.provider}/{ac.model_id}[/]"
                        )

                # Write actors section to the config file
                from pathlib import Path as _Path

                import yaml as _yaml

                config_path = _Path(result.config_path)
                if config_path.exists():
                    config_data = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    config_data["actors"] = {
                        wf: {name: ac.to_dict() for name, ac in actors.items()}
                        for wf, actors in actor_configs.items()
                    }
                    config_path.write_text(
                        _yaml.dump(
                            config_data,
                            default_flow_style=False,
                            sort_keys=False,
                        ),
                        encoding="utf-8",
                    )

            # Success message
            console.print()
            console.print(f"[green]✓[/] Configuration written to [bold]{result.config_path}[/]")

            # Suggest runway seed if runway initialized and providers available
            if (
                result.runway_initialized
                and result.provider_discovery
                and result.provider_discovery.found_providers
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

        except ConfigExistsError as e:
            err_console.print(f"[red]Error:[/red] {e.config_path} already exists.")
            err_console.print()
            err_console.print("Use [bold]--force[/] to overwrite the existing configuration.")
            raise SystemExit(CONFIG_EXISTS_EXIT_CODE) from None
