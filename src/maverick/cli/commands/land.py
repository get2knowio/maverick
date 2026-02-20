"""``maverick land`` command.

Curate commit history and push after ``maverick fly`` finishes.

Three modes:
  - **Approve** (default):  curate → push → optional PR → teardown workspace.
  - **Eject** (``--eject``):  curate → push preview branch → keep workspace.
  - **Finalize** (``--finalize``):  create PR from preview branch → teardown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.panel import Panel
from rich.table import Table

from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_success, format_warning
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--no-curate",
    is_flag=True,
    default=False,
    help="Skip curation, just push.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show curation plan without executing.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Auto-approve curation plan.",
)
@click.option(
    "--base",
    default="main",
    show_default=True,
    help="Base revision for curation scope.",
)
@click.option(
    "--heuristic-only",
    is_flag=True,
    default=False,
    help="Use heuristic curation (no agent).",
)
@click.option(
    "--eject",
    is_flag=True,
    default=False,
    help="Skip approval; push to a preview branch and keep workspace.",
)
@click.option(
    "--finalize",
    is_flag=True,
    default=False,
    help="Finalize after eject: create PR, cleanup workspace.",
)
@click.option(
    "--branch",
    default=None,
    help="Branch name for the pushed bookmark (default: maverick/<project>).",
)
@click.pass_context
@async_command
async def land(
    ctx: click.Context,
    no_curate: bool,
    dry_run: bool,
    yes: bool,
    base: str,
    heuristic_only: bool,
    eject: bool,
    finalize: bool,
    branch: str | None,
) -> None:
    """Curate commit history and push.

    Finalizes work from 'maverick fly' by reorganizing commits into
    clean history and pushing to remote.

    Three modes of operation:

    \b
      maverick land             # curate → approve → push → cleanup
      maverick land --eject     # curate → push preview branch
      maverick land --finalize  # create PR from preview → cleanup

    Examples:

    \b
        maverick land
        maverick land --dry-run
        maverick land --no-curate
        maverick land --heuristic-only
        maverick land --eject
        maverick land --finalize
        maverick land --yes
    """
    if finalize:
        await _finalize(base=base, branch=branch)
        return

    from maverick.library.actions.jj import (
        curate_history,
        gather_curation_context,
    )
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    project_name = user_repo.name
    manager = WorkspaceManager(user_repo_path=user_repo)
    ws_path = manager.workspace_path
    cwd: Path | None = ws_path if manager.exists else None

    if not manager.exists:
        console.print(
            format_warning("No workspace found. Operating in current directory.")
        )

    # ── 1. Check there are commits to land ──────────────────────────
    curation_ctx = await gather_curation_context(base, cwd=cwd)
    if not curation_ctx["success"]:
        err_console.print(
            format_error(
                f"Failed to gather commit context: {curation_ctx['error']}",
            )
        )
        raise SystemExit(ExitCode.FAILURE)

    commits = curation_ctx["commits"]
    if not commits:
        console.print("Nothing to land — no commits found above base revision.")
        return

    console.print(f"Found {len(commits)} commit(s) above [bold]{base}[/bold].")

    # ── 2. Curation ────────────────────────────────────────────────
    if no_curate:
        console.print("Skipping curation (--no-curate).")
    elif heuristic_only:
        console.print("Running heuristic curation...")
        result = await curate_history(base, cwd=cwd)
        if result["success"]:
            absorb = "yes" if result["absorb_ran"] else "no"
            squashed = result["squashed_count"]
            console.print(
                f"Heuristic curation: absorb={absorb}, squashed={squashed} commits."
            )
        else:
            err_console.print(
                format_error(
                    f"Heuristic curation failed: {result['error']}",
                )
            )
            raise SystemExit(ExitCode.FAILURE)
    else:
        # Agent-driven curation
        await _agent_curate(
            curation_ctx=curation_ctx,
            base=base,
            dry_run=dry_run,
            auto_approve=yes,
            cwd=cwd,
        )

    if dry_run:
        console.print("Dry run — skipping push.")
        return

    # ── 3. Push via jj or git ──────────────────────────────────────
    if eject:
        await _eject(
            manager=manager,
            project_name=project_name,
            base=base,
            commits=commits,
            branch=branch,
            cwd=cwd,
            user_repo=user_repo,
        )
    else:
        await _approve(
            manager=manager,
            project_name=project_name,
            base=base,
            commits=commits,
            branch=branch,
            yes=yes,
            cwd=cwd,
            user_repo=user_repo,
        )


# =====================================================================
# Approve path
# =====================================================================


async def _approve(
    manager: Any,
    project_name: str,
    base: str,
    commits: list[Any],
    branch: str | None,
    yes: bool,
    cwd: Path | None,
    user_repo: Path | None = None,
) -> None:
    """Approve: set bookmark, push, optionally create PR, teardown."""
    from maverick.jj.client import JjClient

    branch_name = branch or f"maverick/{project_name}"

    if not yes:
        console.print(
            f"\n  Proposed: {len(commits)} curated commit(s) "
            f"on branch [bold]{branch_name}[/bold]\n"
        )
        answer = console.input(
            "  [A]pprove and push  [E]ject to git branch  [C]ancel? "
        )
        choice = answer.strip().lower()[:1]
        if choice == "e":
            await _eject(
                manager=manager,
                project_name=project_name,
                base=base,
                commits=commits,
                branch=branch,
                cwd=cwd,
            )
            return
        if choice != "a":
            console.print("Cancelled.")
            raise SystemExit(ExitCode.SUCCESS)

    # Push via jj if workspace exists, otherwise git push
    if cwd is not None:
        client = JjClient(cwd=cwd)
        try:
            await client.bookmark_set(branch_name, revision="@-")
            # Phase 1: jj push from workspace → user repo (workspace's origin)
            await client.git_push(bookmark=branch_name)
        except Exception as e:
            err_console.print(format_error(f"Push failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e

        # Phase 2: push from user repo → remote origin
        # The jj push above lands commits in the user repo as a local branch.
        # We still need to push that branch to the actual remote.
        repo_path = user_repo or Path.cwd().resolve()
        try:
            from maverick.runners.command import CommandRunner

            runner = CommandRunner(timeout=60.0)
            result = await runner.run(
                ["git", "push", "--set-upstream", "origin", branch_name],
                cwd=repo_path,
            )
            if not result.success:
                err_console.print(
                    format_error(f"Push to origin failed: {result.stderr.strip()}")
                )
                raise SystemExit(ExitCode.FAILURE)
        except SystemExit:
            raise
        except Exception as e:
            err_console.print(format_error(f"Push to origin failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e
    else:
        from maverick.library.actions.git import git_push

        push_result = await git_push(set_upstream=True)
        if not push_result["success"]:
            err_console.print(format_error(f"Push failed: {push_result['error']}"))
            raise SystemExit(ExitCode.FAILURE)

    console.print(
        format_success(f"Landed {len(commits)} commit(s) on branch {branch_name}.")
    )

    # Teardown workspace
    if manager.exists:
        await manager.teardown()
        console.print("Workspace cleaned up.")


# =====================================================================
# Eject path
# =====================================================================


async def _eject(
    manager: Any,
    project_name: str,
    base: str,
    commits: list[Any],
    branch: str | None,
    cwd: Path | None,
    user_repo: Path | None = None,
) -> None:
    """Eject: push to a preview branch and keep workspace."""
    from maverick.workspace.models import WorkspaceState

    preview_branch = branch or f"maverick/preview/{project_name}"

    if cwd is not None:
        from maverick.jj.client import JjClient

        client = JjClient(cwd=cwd)
        try:
            await client.bookmark_set(preview_branch, revision="@-")
            # Phase 1: jj push from workspace → user repo
            await client.git_push(bookmark=preview_branch)
        except Exception as e:
            err_console.print(format_error(f"Eject push failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e

        # Phase 2: push from user repo → remote origin
        repo_path = user_repo or Path.cwd().resolve()
        try:
            from maverick.runners.command import CommandRunner

            runner = CommandRunner(timeout=60.0)
            result = await runner.run(
                ["git", "push", "--set-upstream", "origin", preview_branch],
                cwd=repo_path,
            )
            if not result.success:
                err_console.print(
                    format_error(
                        f"Push to origin failed: {result.stderr.strip()}"
                    )
                )
                raise SystemExit(ExitCode.FAILURE)
        except SystemExit:
            raise
        except Exception as e:
            err_console.print(format_error(f"Push to origin failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e

        # Mark workspace as ejected (not deleted)
        manager.set_state(WorkspaceState.EJECTED)
    else:
        from maverick.library.actions.git import git_push

        push_result = await git_push(set_upstream=True)
        if not push_result["success"]:
            err_console.print(format_error(f"Push failed: {push_result['error']}"))
            raise SystemExit(ExitCode.FAILURE)

    console.print(format_success(f"Ejected to branch: {preview_branch}"))
    console.print(
        f"Run [bold]maverick land --finalize --branch {preview_branch}[/bold] "
        "when ready."
    )


# =====================================================================
# Finalize path
# =====================================================================


async def _finalize(
    base: str,
    branch: str | None,
) -> None:
    """Finalize after eject: create PR from preview branch, cleanup."""
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    project_name = user_repo.name
    preview_branch = branch or f"maverick/preview/{project_name}"

    console.print(f"Finalizing from branch [bold]{preview_branch}[/bold]...")

    # Create PR if gh is available
    try:
        from maverick.library.actions.github import create_github_pr

        pr_result = await create_github_pr(
            base_branch=base,
            draft=False,
            generated_body=f"Automated PR from maverick fly for {project_name}.",
            title=f"maverick: {project_name}",
        )
        if pr_result.success:
            console.print(format_success(f"PR created: {pr_result.pr_url or ''}"))
        else:
            console.print(
                format_warning(
                    f"PR creation failed: {pr_result.error or 'unknown'}. "
                    "You can create a PR manually."
                )
            )
    except Exception as e:
        console.print(
            format_warning(f"Could not create PR: {e}. You can create one manually.")
        )

    # Cleanup workspace if it still exists
    manager = WorkspaceManager(user_repo_path=user_repo)
    if manager.exists:
        await manager.teardown()
        console.print("Workspace cleaned up.")
    else:
        console.print("No workspace to clean up.")


# =====================================================================
# Agent curation
# =====================================================================


async def _agent_curate(
    curation_ctx: dict[str, Any],
    base: str,
    dry_run: bool,
    auto_approve: bool,
    cwd: Path | None = None,
) -> None:
    """Run agent-driven curation with interactive approval.

    Args:
        curation_ctx: Output of gather_curation_context().
        base: Base revision.
        dry_run: If True, show plan and exit.
        auto_approve: If True, skip the approval prompt.
        cwd: Workspace directory for executing curation commands.

    Raises:
        SystemExit: On failure or user rejection.
    """
    from maverick.library.actions.jj import execute_curation_plan

    console.print("Analyzing commits with curator agent...")

    try:
        from maverick.agents.curator import CuratorAgent

        agent = CuratorAgent()
        raw_output = await agent.generate(
            {
                "commits": curation_ctx["commits"],
                "log_summary": curation_ctx["log_summary"],
            }
        )
        # generate returns str when return_usage=False
        assert isinstance(raw_output, str)
        plan = agent.parse_plan(raw_output)
    except Exception as e:
        err_console.print(
            format_error(
                f"Curator agent failed: {e}",
                suggestion="Try --heuristic-only as a fallback.",
            )
        )
        raise SystemExit(ExitCode.FAILURE) from e

    if not plan:
        console.print("Curator: no curation needed — history looks clean.")
        return

    # Display plan
    _display_plan(plan)

    if dry_run:
        console.print("Dry run — plan not applied.")
        raise SystemExit(ExitCode.SUCCESS)

    # Approval gate
    if not auto_approve:
        answer = console.input("\nApply this plan? [y/N] ")
        if not answer.strip().lower().startswith("y"):
            console.print("Curation cancelled.")
            raise SystemExit(ExitCode.SUCCESS)

    # Execute
    console.print("Applying curation plan...")
    result = await execute_curation_plan(plan, cwd=cwd)
    if result["success"]:
        console.print(
            f"Curation complete: "
            f"{result['executed_count']}/{result['total_count']} "
            f"operations applied."
        )
    else:
        err_console.print(
            format_error(
                f"Curation failed: {result['error']}",
                details=[
                    f"Executed {result['executed_count']}"
                    f"/{result['total_count']} steps.",
                    f"Snapshot ID: {result['snapshot_id']} (for manual recovery).",
                ],
                suggestion=("Repository was rolled back to pre-curation state."),
            )
        )
        raise SystemExit(ExitCode.FAILURE)


def _display_plan(plan: list[dict[str, Any]]) -> None:
    """Render the curation plan as a Rich table inside a panel.

    Args:
        plan: List of plan step dicts.
    """
    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Command", width=30)
    table.add_column("Reason")

    for i, step in enumerate(plan, 1):
        cmd_str = f"jj {step['command']} {' '.join(step.get('args', []))}"
        table.add_row(str(i), cmd_str, step.get("reason", ""))

    panel = Panel(
        table,
        title=(f"Curation Plan ({len(plan)} operation{'s' if len(plan) != 1 else ''})"),
        border_style="cyan",
    )
    console.print(panel)
