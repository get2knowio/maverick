"""``maverick fly`` command.

Bead-driven development workflow — picks the next ready bead(s) and
iterates: implement, validate, review, commit, close, repeat.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal as _signal
from collections.abc import AsyncIterator
from pathlib import Path

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.workflow_executor import (
    PythonWorkflowRunConfig,
    _display_name,
    execute_python_workflow,
)
from maverick.workflows.fly_beads import FlyBeadsWorkflow
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    GATE_CHECK,
    GATE_REMEDIATION,
    IMPLEMENT_AND_VALIDATE,
    PREFLIGHT,
    REVIEW,
    SELECT_BEAD,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.graceful_stop import (
    request_graceful_stop,
    reset_graceful_stop,
)


@contextlib.asynccontextmanager
async def _graceful_sigint() -> AsyncIterator[None]:
    """Two-stage SIGINT handler for ``maverick fly``.

    * **First Ctrl-C**: set the graceful-stop flag so the supervisor
      exits cleanly after the current bead. Print a hint that a second
      Ctrl-C will bail immediately.
    * **Second Ctrl-C**: cancel the awaiting task so ``CancelledError``
      propagates and tears the run down. Completed bead commits stay in
      the user repo's working state — they're real local jj/git commits
      that ``maverick land`` (or a manual ``git push``) can pick up.

    Falls back to a no-op on platforms without
    ``loop.add_signal_handler`` support (Windows).
    """
    loop = asyncio.get_running_loop()
    current_task = asyncio.current_task()
    state: dict[str, int] = {"count": 0}

    def _on_sigint() -> None:
        state["count"] += 1
        if state["count"] == 1:
            request_graceful_stop()
            console.print()
            console.print(
                "[yellow]Stopping after current bead completes. "
                "Press Ctrl-C again to bail immediately.[/]"
            )
        else:
            console.print()
            console.print("[red]Aborting now.[/]")
            if current_task is not None:
                current_task.cancel()

    try:
        loop.add_signal_handler(_signal.SIGINT, _on_sigint)
    except NotImplementedError:
        # Windows: no add_signal_handler. Default Ctrl-C behaviour
        # (KeyboardInterrupt) is the only fallback available.
        yield
        return

    try:
        yield
    finally:
        with contextlib.suppress(NotImplementedError, ValueError, RuntimeError):
            loop.remove_signal_handler(_signal.SIGINT)
        reset_graceful_stop()


# Ordered list of fly-beads steps for --list-steps display.
_FLY_BEADS_STEPS = [
    PREFLIGHT,
    SNAPSHOT_UNCOMMITTED,
    SELECT_BEAD,
    IMPLEMENT_AND_VALIDATE,
    GATE_CHECK,
    GATE_REMEDIATION,
    REVIEW,
    COMMIT,
]


def _verify_isolation_ready(cwd: Path) -> None:
    """The two isolated-mode preconditions cheap and useful to check
    before any bead is selected (contract fly-isolated-mode.md).

    ``.jj/`` and the ``jj`` binary fail fast here with a friendly
    message; a held run lock or a stale application journal are instead
    left to surface naturally as ``IsolationLockedError`` /
    ``IsolationRecoveryRequiredError`` once the run actually starts (see
    the caller's comment — same non-zero-exit guarantee, no duplicate
    check to keep in sync).
    """
    if not (cwd / ".jj").is_dir():
        console.print(
            "[red]Error:[/red] --isolated needs a jj-colocated checkout, "
            f"but no [bold].jj/[/bold] directory was found in {cwd}.\n"
            "Run [cyan]maverick init[/cyan] first."
        )
        raise SystemExit(ExitCode.FAILURE)

    import shutil

    if shutil.which("jj") is None:
        console.print(
            "[red]Error:[/red] --isolated requires the [bold]jj[/bold] binary "
            "on PATH, but it was not found.\n"
            "Install jj: https://jj-vcs.github.io/jj/latest/install-and-setup/"
        )
        raise SystemExit(ExitCode.FAILURE)


@click.command()
@click.option(
    "--epic",
    default=None,
    help="Epic bead ID to iterate over (omit to pick any ready bead).",
)
@click.option(
    "--max-beads",
    default=0,
    show_default=True,
    type=int,
    help="Maximum number of beads to process (0 = unlimited; drain the queue).",
)
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--auto-commit",
    is_flag=True,
    default=False,
    help="Automatically commit uncommitted changes before cloning workspace.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.option(
    "--watch",
    is_flag=True,
    default=False,
    help="Keep running and poll for new beads when queue is empty.",
)
@click.option(
    "--watch-interval",
    type=int,
    default=30,
    show_default=True,
    help="Seconds between polls when no beads are ready (requires --watch).",
)
@click.option(
    "--skip-preflight",
    is_flag=True,
    default=False,
    help=(
        "Skip the pre-flight checks (provider health, git config, etc.). "
        "Testing only — runtime failures will surface mid-flight instead."
    ),
)
@click.option(
    "--isolated/--no-isolated",
    "isolated_flag",
    default=None,
    help=(
        "Run each bead's agent steps in its own isolated jj workspace "
        "(057-isolated-bead-workspaces). Overrides the maverick.yaml "
        "'workspace.enabled' config key; omit to use that config's value "
        "(default: off)."
    ),
)
@click.pass_context
@async_command
async def fly(
    ctx: click.Context,
    epic: str | None,
    max_beads: int,
    list_steps: bool,
    auto_commit: bool,
    session_log: Path | None,
    watch: bool,
    watch_interval: int,
    skip_preflight: bool,
    isolated_flag: bool | None,
) -> None:
    """Run a bead-driven development workflow.

    Iterates over ready beads: selects the next bead, implements it,
    validates, reviews, commits, closes, and repeats until all beads
    are done.

    When --epic is provided, only beads under that epic are considered.
    When omitted, any ready bead across all epics may be selected.

    With --watch, fly keeps running and polls for new beads when the
    queue is empty. This enables concurrent plan/refuel in another
    terminal while fly continuously drains work.

    With --isolated, every bead's agent steps run in their own isolated
    jj workspace rather than directly in the checkout
    (057-isolated-bead-workspaces) — see the project README for details.

    Examples:
        maverick fly
        maverick fly --epic my-epic
        maverick fly --max-beads 5
        maverick fly --watch
        maverick fly --isolated
    """
    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(_FLY_BEADS_STEPS, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    # Preflight: bd installed AND .beads initialized. Fly closes beads
    # at the end of every successful round, so a missing bd setup would
    # only surface mid-workflow (after expensive implementer + reviewer
    # work) without this check. ``--skip-preflight`` bypasses both this
    # CLI-level check and the in-workflow PREFLIGHT step.
    if skip_preflight:
        console.print(
            "[yellow]Warning:[/yellow] --skip-preflight is set; "
            "provider/git/jj/bd checks will not run. "
            "Failures will surface mid-flight."
        )
    else:
        from maverick.cli.common import verify_bd_ready

        verify_bd_ready()

    # Fly runs in the user's checkout. ``maverick init`` makes the
    # cwd jj+git colocated so per-bead jj commits land directly on
    # the user's current branch.
    cwd = Path.cwd().resolve()

    # 057-isolated-bead-workspaces: --isolated/--no-isolated overrides
    # workspace.enabled; absent both, behavior is unchanged (FR-035,
    # SC-011). Preconditions are checked here, before any bead is
    # selected (contract fly-isolated-mode.md) — .jj/ and the jj binary
    # fail fast and cheaply; a held lock or a stale application journal
    # instead surface naturally as IsolationLockedError /
    # IsolationRecoveryRequiredError once the run actually starts (both
    # MaverickError subclasses with an actionable .message, already
    # rendered as a non-zero-exit refusal by cli_error_handler — no
    # separate check needed here to get the same "no silent fallback"
    # guarantee).
    from maverick.config import lookup_workspace_config

    config = (ctx.obj or {}).get("config") if ctx.obj else None
    if config is None:
        from maverick.config import load_config

        config = load_config()
    isolated = (
        isolated_flag if isolated_flag is not None else lookup_workspace_config(config).enabled
    )

    if isolated:
        _verify_isolation_ready(cwd)

    async with _graceful_sigint():
        await execute_python_workflow(
            ctx,
            PythonWorkflowRunConfig(
                workflow_class=FlyBeadsWorkflow,
                inputs={
                    "epic_id": epic or "",
                    "max_beads": max_beads,
                    "auto_commit": auto_commit,
                    "watch": watch,
                    "watch_interval": watch_interval,
                    "skip_preflight": skip_preflight,
                    "cwd": str(cwd),
                    "isolated": isolated,
                },
                session_log_path=session_log,
            ),
        )
