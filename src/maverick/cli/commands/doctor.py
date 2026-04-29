"""``maverick doctor`` command — standalone environment validation.

Runs the same checks as fly's preflight (ACP provider handshake +
prompt verification, git / gh / bd availability) but without burning
a real fly invocation. Useful when iterating on ``maverick.yaml``,
swapping providers, or troubleshooting auth issues.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import click
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table

from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.library.actions.preflight import run_preflight_checks
from maverick.runners.provider_health import build_provider_health_checks


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

    Exit code 0 if all checks pass, 1 otherwise. Provider checks run
    in parallel with a live progress table — every configured provider
    is exercised, even if an earlier one fails. Each provider gets a
    tiny "say ok" prompt so auth/quota issues surface here instead of
    mid-flight.

    Examples:

        maverick doctor

        maverick doctor --providers-only
    """
    config = ctx.obj.get("config") if ctx.obj else None

    console.print("[bold cyan]Maverick Doctor[/]")
    console.print()

    provider_results = await _run_provider_checks(config)

    other_result = None
    if not providers_only:
        other_result = await run_preflight_checks(
            check_providers=False,
            check_git=True,
            check_github=True,
            check_bd=True,
            check_jj=True,
            check_validation_tools=False,
            fail_on_error=False,
            config=config,
        )
        for label, ok in [
            ("git", other_result.git_available),
            ("GitHub CLI", other_result.github_cli_available),
            ("jj (Jujutsu)", other_result.jj_available),
        ]:
            icon = "[green]✓[/]" if ok else "[red]✗[/]"
            console.print(f"{icon} {label}")

    # Aggregate failures across both stages.
    errors: list[str] = []
    for name, (ok, errs, _ms) in provider_results.items():
        if not ok:
            for err in errs:
                errors.append(f"[{name}] {err}")
    if other_result is not None and other_result.errors:
        errors.extend(other_result.errors)

    warnings: list[str] = []
    if other_result is not None and other_result.warnings:
        warnings.extend(other_result.warnings)

    if errors:
        console.print()
        console.print("[bold]Issues:[/]")
        for err in errors:
            err_console.print(f"  [red]✗[/] {err}")

    if warnings:
        console.print()
        console.print("[bold]Warnings:[/]")
        for warning in warnings:
            console.print(f"  [yellow]⚠[/] {warning}")

    console.print()
    if not errors:
        console.print("[green]All checks passed.[/]")
    else:
        err_console.print("[red]One or more checks failed.[/]")
        raise SystemExit(ExitCode.FAILURE)


# ---------------------------------------------------------------------------
# Provider check with live progress
# ---------------------------------------------------------------------------


_ProviderResult = tuple[bool, tuple[str, ...], int]
"""(success, errors, duration_ms) per provider."""


async def _run_provider_checks(config: Any) -> dict[str, _ProviderResult]:
    """Run all provider health checks in parallel with a Rich Live table.

    Each provider gets its own row showing a spinner while the check is
    in flight, then ✓/✗ + timing once it lands. The table updates as
    soon as each individual check completes — failures don't block
    progress on the others.
    """
    if config is None:
        console.print("[yellow]No config loaded — skipping provider checks.[/]")
        return {}

    # Doctor opts in to the MCP tool-call probe. The workflow preflight
    # leaves it off (extra 2-5s/provider) — fly already exercises the
    # MCP path during real bead work, but doctor is the right place to
    # surface bridge bugs before the user spends real tokens.
    health_checks = build_provider_health_checks(config, test_mcp_tool_call=True)
    if not health_checks:
        console.print("[dim]No ACP providers configured.[/]")
        return {}

    console.print("[bold]ACP providers[/]")

    statuses: dict[str, dict[str, Any]] = {
        hc.provider_name: {"state": "running", "timing": "", "detail": ""}
        for hc in health_checks
    }
    results: dict[str, _ProviderResult] = {}

    def render_table() -> Table:
        table = Table(
            show_header=False,
            show_edge=False,
            pad_edge=False,
            box=None,
            padding=(0, 1),
        )
        table.add_column("provider", min_width=14)
        table.add_column("timing", justify="right", min_width=8)
        table.add_column("status", min_width=3)
        table.add_column("detail", overflow="fold")

        for name in statuses:
            info = statuses[name]
            timing = f"[dim]{info['timing']}[/]" if info["timing"] else ""
            if info["state"] == "running":
                table.add_row(
                    f"  [cyan]∟[/] {name}",
                    "",
                    Spinner("dots", style="cyan"),
                    "[dim]checking…[/]",
                )
            elif info["state"] == "ok":
                table.add_row(
                    f"  [green]∟[/] {name}", timing, "[green]✓[/]", "[dim]healthy[/]"
                )
            else:
                detail = f"[red dim]{info['detail']}[/]" if info["detail"] else ""
                table.add_row(
                    f"  [red]∟[/] {name}", timing, "[red]✗[/]", detail
                )
        return table

    async def _runner(hc: Any) -> tuple[str, Any, int]:
        start = time.monotonic()
        result = await hc.validate()
        duration_ms = int((time.monotonic() - start) * 1000)
        return hc.provider_name, result, duration_ms

    with Live(render_table(), console=console, refresh_per_second=10) as live:
        tasks = [asyncio.create_task(_runner(hc)) for hc in health_checks]
        for coro in asyncio.as_completed(tasks):
            name, result, duration_ms = await coro
            errs = tuple(result.errors)
            ok = bool(result.success)
            results[name] = (ok, errs, duration_ms)
            statuses[name] = {
                "state": "ok" if ok else "fail",
                "timing": f"{duration_ms / 1000:.1f}s",
                "detail": _short_detail(errs),
            }
            live.update(render_table())

    return results


def _short_detail(errors: tuple[str, ...]) -> str:
    """Render a one-line failure hint for the live table.

    The full error text shows up in the post-run "Issues" section;
    here we just want a glanceable cause. The health-check error
    messages tend to start with a long ``Provider 'X' …`` prefix
    that's already implicit in the provider row, so strip it.
    """
    if not errors:
        return ""
    first = errors[0]
    # Drop the "Provider 'X' " prefix the health check adds.
    marker = "' "
    if first.startswith("Provider '") and marker in first:
        first = first.split(marker, 1)[1]
    # Cap so the live table doesn't wrap absurdly.
    if len(first) > 80:
        first = first[:77] + "…"
    return first
