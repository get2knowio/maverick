"""``maverick doctor`` command — standalone environment validation.

Runs the same checks as fly's preflight (ACP provider handshake +
prompt verification, git / gh / bd availability) but without burning
a real fly invocation. Useful when iterating on ``maverick.yaml``,
swapping providers, or troubleshooting auth issues.
"""

from __future__ import annotations

import click

from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command


@click.command()
@click.option(
    "--providers-only",
    is_flag=True,
    default=False,
    help="Skip git / gh / jj / bd checks; only validate ACP providers.",
)
@click.pass_context
@async_command
async def doctor(ctx: click.Context, providers_only: bool) -> None:
    """Validate the local environment.

    Exit code 0 if all checks pass, 1 otherwise. The provider check
    sends a tiny "say ok" prompt to each configured provider so that
    auth/quota issues surface here instead of mid-flight.

    Examples:

        maverick doctor

        maverick doctor --providers-only
    """
    from maverick.library.actions.preflight import run_preflight_checks

    config = ctx.obj.get("config") if ctx.obj else None

    console.print("[bold cyan]Maverick Doctor[/]")
    console.print()

    result = await run_preflight_checks(
        check_providers=True,
        check_git=not providers_only,
        check_github=not providers_only,
        check_bd=not providers_only,
        check_jj=not providers_only,
        # Validation tool detection (ruff/mypy/pytest etc.) is project-
        # specific noise for a generic env check — skip it here. Fly
        # still runs it as part of its own preflight.
        check_validation_tools=False,
        fail_on_error=False,
        config=config,
    )

    rows: list[tuple[str, bool]] = [
        ("ACP providers", result.providers_available),
    ]
    if not providers_only:
        rows.extend(
            [
                ("git", result.git_available),
                ("GitHub CLI", result.github_cli_available),
                ("jj (Jujutsu)", result.jj_available),
            ]
        )

    for name, ok in rows:
        icon = "[green]✓[/]" if ok else "[red]✗[/]"
        console.print(f"{icon} {name}")

    if result.errors:
        console.print()
        console.print("[bold]Issues:[/]")
        for err in result.errors:
            err_console.print(f"  [red]✗[/] {err}")

    if result.warnings:
        console.print()
        console.print("[bold]Warnings:[/]")
        for warning in result.warnings:
            console.print(f"  [yellow]⚠[/] {warning}")

    console.print()
    if result.success:
        console.print("[green]All checks passed.[/]")
    else:
        err_console.print("[red]One or more checks failed.[/]")
        raise SystemExit(ExitCode.FAILURE)
