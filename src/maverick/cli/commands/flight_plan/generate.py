"""``maverick plan generate`` command.

Generates a structured flight plan from a PRD using an AI agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import (
    DEFAULT_PLANS_DIR,
    KEBAB_CASE_RE,
    flight_plan,
)
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command


@flight_plan.command("generate")
@click.argument("name", metavar="NAME")
@click.option(
    "--from-prd",
    required=True,
    help="Path to PRD file, or '-' for STDIN.",
)
@click.option(
    "--plans-dir",
    "output_dir",
    default=DEFAULT_PLANS_DIR,
    show_default=True,
    help="Base plans directory.",
)
@click.option(
    "--skip-briefing",
    is_flag=True,
    default=False,
    help="Skip the pre-flight briefing room consultation.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.pass_context
@async_command
async def generate(
    ctx: click.Context,
    name: str,
    from_prd: str,
    output_dir: str,
    skip_briefing: bool,
    session_log: Path | None,
) -> None:
    """Generate a flight plan from a PRD using an AI agent.

    NAME must be a kebab-case identifier: lowercase letters, digits, and
    hyphens only, starting with a letter and not ending with a hyphen.

    The --from-prd option accepts a file path or '-' for STDIN.

    Examples:

        maverick plan generate my-feature --from-prd spec.md

        cat spec.md | maverick plan generate my-feature --from-prd -

    Output: .maverick/plans/{name}/flight-plan.md
    """
    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.generate_flight_plan import GenerateFlightPlanWorkflow
    from maverick.workspace.manager import WorkspaceManager

    # Validate kebab-case name.
    if not KEBAB_CASE_RE.match(name):
        console.print(
            f"[red]Error:[/red] Invalid flight plan name '[bold]{name}[/bold]'.\n"
            "Name must be kebab-case: lowercase letters, digits, and hyphens only,\n"
            "starting with a letter and not ending with a hyphen.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Read PRD content (from user repo — read-only crossover is allowed
    # under Architecture A).
    if from_prd == "-":
        prd_content = sys.stdin.read()
    else:
        prd_path = Path(from_prd)
        if not prd_path.exists():
            console.print(
                f"[red]Error:[/red] PRD file not found: '[bold]{from_prd}[/bold]'.",
            )
            raise SystemExit(ExitCode.FAILURE)
        prd_content = prd_path.read_text(encoding="utf-8")

    if not prd_content.strip():
        console.print("[red]Error:[/red] PRD content is empty.")
        raise SystemExit(ExitCode.FAILURE)

    # Architecture A: plan generation operates inside the workspace.
    # Find or create the workspace before resolving plan paths so
    # existence checks and writes target the workspace, not the user repo.
    # Graceful fallback: if the user's directory isn't a real git repo
    # (e.g. tests, quick prototyping), operate against user cwd instead
    # of failing — the workspace bridge isn't load-bearing for input
    # validation.
    from maverick.workspace.errors import WorkspaceError

    user_repo = Path.cwd().resolve()
    ws_manager = WorkspaceManager(user_repo_path=user_repo)
    workspace_path: Path | None = None
    workflow_cwd: str | None = None
    try:
        workspace_ctx = await ws_manager.find_or_create()
        workspace_path = workspace_ctx.path
        workflow_cwd = str(workspace_ctx.path)
    except WorkspaceError as exc:
        # Workspace creation failed (typically: user dir is not a git
        # repo). Fall back to user cwd for path resolution; the workflow
        # will run in user cwd.
        from maverick.logging import get_logger

        get_logger(__name__).debug(
            "plan_generate_workspace_unavailable",
            error=str(exc),
            user_repo=str(user_repo),
        )
        workspace_path = user_repo

    # Resolve output_dir relative to the workspace (or user repo if
    # fallback). Absolute paths are honored as-is.
    plans_input = Path(output_dir)
    plans_path = plans_input if plans_input.is_absolute() else workspace_path / plans_input

    # Guard: --plans-dir must not point to an existing regular file.
    if plans_path.exists() and not plans_path.is_dir():
        console.print(
            f"[red]Error:[/red] '[bold]{plans_path}[/bold]' exists but is not a directory.",
        )
        raise SystemExit(ExitCode.FAILURE)

    plan_dir = plans_path / name
    target_file = plan_dir / "flight-plan.md"

    # Overwrite guard: refuse if file already exists.
    if target_file.exists():
        console.print(
            f"[red]Error:[/red] Flight plan '[bold]{name}[/bold]' already exists at "
            f"[dim]{target_file}[/dim].\n"
            "Delete the file or choose a different name to proceed.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Execute the workflow with absolute paths inside the workspace.
    workflow_inputs: dict[str, object] = {
        "prd_content": prd_content,
        "name": name,
        "output_dir": str(plans_path),
        "skip_briefing": skip_briefing,
    }
    if workflow_cwd is not None:
        workflow_inputs["cwd"] = workflow_cwd

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=GenerateFlightPlanWorkflow,
            inputs=workflow_inputs,
            session_log_path=session_log,
        ),
    )

    # Hermetic command exit ramp: commit the plan in the workspace,
    # push it to the user repo, merge into the current branch, and tear
    # the workspace down. Skipped when we fell back to operating in the
    # user cwd (no workspace was created).
    if workflow_cwd is not None:
        await ws_manager.finalize(message=f"chore: add flight plan for {name}")
        from maverick.cli.common import resolve_publish_branch_label

        branch_label = await resolve_publish_branch_label(user_repo)
        console.print(f"[green]✓[/] Plan published to user repo (branch: {branch_label})")
