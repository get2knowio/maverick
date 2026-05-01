"""``maverick refuel`` command.

Decomposes a flight plan into beads (work units) using the Thespian
actor system for parallel agent execution.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import DEFAULT_PLANS_DIR
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command


@click.command()
@click.argument("name")
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.option(
    "--skip-briefing",
    is_flag=True,
    default=False,
    help="Skip the briefing room step (parallel agent analysis).",
)
@click.option(
    "--auto-commit",
    is_flag=True,
    default=False,
    help=(
        "Commit any uncommitted changes (including refuel's own output) "
        "after refuel succeeds. Lets ``maverick fly`` pick up the work "
        "without tripping the snapshot check."
    ),
)
@click.option(
    "--plans-dir",
    default=DEFAULT_PLANS_DIR,
    show_default=True,
    help="Base plans directory.",
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    name: str,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
    auto_commit: bool,
    plans_dir: str,
) -> None:
    """Decompose a flight plan into beads.

    NAME is a kebab-case plan name. The flight plan is read from
    .maverick/plans/<name>/flight-plan.md.

    Examples:

        maverick refuel my-feature

        maverick refuel my-feature --skip-briefing
    """
    # Preflight: bd installed AND .beads initialized. Catches missing
    # setup in seconds rather than after the full briefing+decompose
    # burn (which we just spent ~13 minutes learning to fail at the
    # bead-creation step).
    from maverick.cli.common import verify_bd_ready

    verify_bd_ready()

    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow
    from maverick.workflows.refuel_maverick.constants import (
        BRIEFING,
        CREATE_BEADS,
        DECOMPOSE,
        GATHER_CONTEXT,
        PARSE_FLIGHT_PLAN,
        VALIDATE,
        WIRE_DEPS,
        WORKFLOW_NAME,
        WRITE_WORK_UNITS,
    )

    steps = [
        PARSE_FLIGHT_PLAN,
        GATHER_CONTEXT,
        BRIEFING,
        DECOMPOSE,
        VALIDATE,
        WRITE_WORK_UNITS,
        CREATE_BEADS,
        WIRE_DEPS,
    ]

    if list_steps:
        from maverick.cli.workflow_executor import _display_name

        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    # Architecture A: refuel attaches to (or creates) the workspace and
    # operates entirely inside it. Plans and beads live in the workspace
    # until ``maverick land`` pushes them to the user repo.
    from maverick.workspace.errors import WorkspaceError
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    ws_manager = WorkspaceManager(user_repo_path=user_repo)
    workspace_path: Path | None = None
    workflow_cwd: str | None = None
    try:
        workspace_ctx = await ws_manager.find_or_create()
        workspace_path = workspace_ctx.path
        workflow_cwd = str(workspace_ctx.path)
    except WorkspaceError as exc:
        # Fall back to user cwd if workspace creation fails (e.g. not a
        # real git repo, jj unavailable). Refuel still works against
        # whatever directory the user is in.
        from maverick.logging import get_logger

        get_logger(__name__).debug(
            "refuel_workspace_unavailable",
            error=str(exc),
            user_repo=str(user_repo),
        )
        workspace_path = user_repo

    # Resolve flight_plan_path inside the workspace (or user repo if
    # fallback). Absolute plans_dir overrides workspace resolution.
    plans_input = Path(plans_dir)
    plans_base = plans_input if plans_input.is_absolute() else workspace_path / plans_input
    flight_plan_path = plans_base / name / "flight-plan.md"

    workflow_inputs: dict[str, object] = {
        "flight_plan_path": str(flight_plan_path),
        "skip_briefing": skip_briefing,
        "auto_commit": auto_commit,
    }
    if workflow_cwd is not None:
        workflow_inputs["cwd"] = workflow_cwd

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelMaverickWorkflow,
            inputs=workflow_inputs,
            session_log_path=session_log,
        ),
    )

    # Hermetic command exit ramp: commit the beads + work units in the
    # workspace, push to the user repo, merge into the current branch,
    # and tear the workspace down. Skipped when we fell back to
    # operating in the user cwd (no workspace was created).
    if workflow_cwd is not None:
        await ws_manager.finalize(message=f"chore: refuel {name}")
        console.print(
            f"[green]✓[/] Beads published to user repo (branch: maverick/{user_repo.name})"
        )

    # Surface the "what next" command. The workflow writes the bd epic id
    # into ``.maverick/runs/<run_id>/metadata.json`` — read it back so the
    # user doesn't have to dig for it (it's not the same as the plan name).
    from maverick.runway.run_metadata import find_latest_run

    meta = find_latest_run(name)
    if meta and meta.epic_id:
        console.print()
        console.print(f"[dim]Next:[/] [bold]maverick fly --epic {meta.epic_id}[/]")
