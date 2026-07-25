"""``maverick init`` command — project initialization.

Validates prerequisites, detects project type from marker files,
discovers installed airframe adapters via
:func:`maverick.init.provider_discovery.discover_providers`, and writes
a complete ``maverick.yaml`` (project metadata + ``agents:`` defaults
+ ``validation`` defaults).
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
    PreflightStatus,
    ProjectType,
    ProviderDiscoveryResult,
    run_init,
)
from maverick.init.provider_discovery import (
    parse_model_specs,
    parse_provider_list,
    validate_provider_ids,
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
    discovery: ProviderDiscoveryResult | None,
) -> list[str]:
    """Format airframe-discovered provider output."""
    if discovery is None:
        return [
            "[bold]Connected Providers[/]",
            "  [yellow]Warning:[/yellow] provider discovery failed; "
            "edit the agents: block in maverick.yaml manually.",
            "",
        ]

    lines: list[str] = ["[bold]Connected Providers[/]"]

    if not discovery.providers:
        lines.append("  [yellow]Warning:[/yellow] No providers connected.")
        lines.append(
            "  Install an adapter with [bold]pip install airframe-agents[<extra>][/] "
            "and authenticate per the adapter's docs."
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


def _format_speckit_output(result: InitResult) -> list[str]:
    """Format the Spec Kit install-offer notice (R7/US5).

    Silent (no output) when Spec Kit was already installed and compatible
    — ``speckit_installed`` is only ``None`` in that case *or* when the
    offer was skipped/declined, so a check against the live prerequisite
    result decides which of those it was.
    """
    if result.speckit_installed is True:
        return ["[green]✓[/] Spec Kit installed.", ""]
    if result.speckit_installed is False:
        return [
            "[yellow]Warning:[/yellow] Spec Kit install failed — "
            "`maverick spec` will be unavailable until it's installed manually.",
            "",
        ]

    # speckit_installed is None: either already fine, or the offer was
    # skipped/declined — only the latter needs a user-visible notice.
    from maverick.init.prereqs import check_speckit_installed

    check = check_speckit_installed(Path(result.config_path).parent)
    if check.status != PreflightStatus.PASS:
        return [
            f"[yellow]Notice:[/yellow] {check.message} — "
            "`maverick spec` will be unavailable until Spec Kit is installed.",
            "",
        ]
    return []


def _format_skill_install_output(result: InitResult) -> list[str]:
    """Format the maverick-review skill install notice (053).

    Always-on, always-overwrite step — silent when not applicable
    (``None``), otherwise a single success/warning line.
    """
    if result.skill_installed is True:
        return [
            "[green]✓[/] Installed the maverick-review skill "
            "(.claude/skills/maverick-review/SKILL.md).",
            "",
        ]
    if result.skill_installed is False:
        return [
            "[yellow]Warning:[/yellow] Failed to install the maverick-review skill "
            "— `/maverick-review` will be unavailable until it's installed manually.",
            "",
        ]
    return []


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
    "--providers",
    type=str,
    default=None,
    help=(
        "Comma-separated Airframe provider IDs to spread across "
        "(e.g. claude,github-copilot,opencode,opencode-go)."
    ),
)
@click.option(
    "--models",
    "model_specs",
    type=str,
    multiple=True,
    help=("Provider model specs: provider:model1,model2. May be passed multiple times."),
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
    providers: str | None,
    model_specs: tuple[str, ...],
    verbose: bool,
) -> None:
    """Initialize maverick configuration for the current project.

    Detects project type from marker files, probes installed airframe
    adapters for connected providers, and writes a maverick.yaml with
    per-role airframe bindings under the ``agents:`` block.

    Examples:

        maverick init

        maverick init --type python

        maverick init --providers claude,github-copilot,opencode-go

        maverick init --models opencode-go:minimax-m2.7 --models github-copilot:gpt-5-mini

        maverick init --force -v
    """
    console.print("[bold cyan]Maverick Init[/]")
    console.print()

    type_override: ProjectType | None = None
    if project_type:
        type_override = ProjectType.from_string(project_type)

    try:
        provider_ids = parse_provider_list(providers)
        parsed_model_specs = parse_model_specs(model_specs)

        explicitly_named = set(provider_ids or ())
        explicitly_named.update(parsed_model_specs)
        if explicitly_named:
            validate_provider_ids(tuple(sorted(explicitly_named)))

        if provider_ids is not None:
            model_only = sorted(set(parsed_model_specs) - set(provider_ids))
            if model_only:
                raise ValueError(
                    "--models specified provider(s) not present in --providers: "
                    + ", ".join(model_only)
                )
        elif parsed_model_specs:
            provider_ids = tuple(parsed_model_specs)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    with cli_error_handler():
        try:
            result = await run_init(
                project_path=Path.cwd(),
                type_override=type_override,
                force=force,
                verbose=verbose,
                provider_ids=provider_ids,
                model_specs=parsed_model_specs,
            )

            lines: list[str] = []
            lines.extend(_format_preflight_output(result, verbose))
            lines.extend(_format_detection_output(result, verbose))
            lines.extend(_format_provider_output(result.provider_discovery))
            lines.extend(_format_git_output(result, verbose))
            lines.extend(_format_speckit_output(result))
            lines.extend(_format_skill_install_output(result))
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
