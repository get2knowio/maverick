"""``maverick land`` command.

Curate commit history and apply to local repo after ``maverick fly`` finishes.

Three modes:
  - **Approve** (default):  curate → merge into local repo → teardown workspace.
  - **Eject** (``--eject``):  curate → create local preview branch → keep workspace.
  - **Finalize** (``--finalize``):  merge preview branch → teardown.
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
    help="Skip curation, just merge.",
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
    help="Skip approval; create a local preview branch and keep workspace.",
)
@click.option(
    "--finalize",
    is_flag=True,
    default=False,
    help="Finalize after eject: merge preview branch, cleanup workspace.",
)
@click.option(
    "--no-consolidate",
    is_flag=True,
    default=False,
    help="Skip runway consolidation.",
)
@click.option(
    "--branch",
    default=None,
    help="Branch name for the local bookmark (default: maverick/<project>).",
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
    no_consolidate: bool,
    branch: str | None,
) -> None:
    """Curate commit history and apply to local repo.

    Finalizes work from 'maverick fly' by reorganizing commits into
    clean history and merging them into your local repo.

    Three modes of operation:

    \b
      maverick land             # curate → merge into local repo → cleanup
      maverick land --eject     # curate → create local preview branch
      maverick land --finalize  # merge preview branch → cleanup

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
        await _finalize(base=base, branch=branch, no_consolidate=no_consolidate)
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
        console.print(format_warning("No workspace found. Operating in current directory."))

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

    # ── 1b. Display human review manifest if present ─────────────
    _display_human_review_manifest(cwd or user_repo)

    # ── 2. Curation ────────────────────────────────────────────────
    if no_curate:
        console.print("Skipping curation (--no-curate).")
    elif heuristic_only:
        console.print("Running heuristic curation...")
        result = await curate_history(base, cwd=cwd)
        if result["success"]:
            absorb = "yes" if result["absorb_ran"] else "no"
            squashed = result["squashed_count"]
            console.print(f"Heuristic curation: absorb={absorb}, squashed={squashed} commits.")
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
        console.print("Dry run — skipping merge.")
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
            no_consolidate=no_consolidate,
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
    no_consolidate: bool = False,
) -> None:
    """Approve: push workspace commits to user repo and merge locally."""
    from maverick.jj.client import JjClient
    from maverick.jj.errors import JjError

    branch_name = branch or f"maverick/{project_name}"

    if not yes:
        console.print(f"\n  Proposed: {len(commits)} curated commit(s) to merge into local repo\n")
        answer = console.input("  [A]pprove and merge  [E]ject to git branch  [C]ancel? ")
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

    repo_path = user_repo or Path.cwd().resolve()

    if cwd is not None:
        # Phase 1: jj push from workspace → user repo (creates local branch)
        client = JjClient(cwd=cwd)
        try:
            await client.bookmark_set(branch_name, revision="@-")
            await client.git_push(bookmark=branch_name)
        except JjError as e:
            err_console.print(format_error(f"Push to local repo failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e

        # Phase 2: merge the branch into the user's current branch
        from maverick.library.actions.git import git_merge

        merge_result = await git_merge(branch_name, cwd=repo_path)
        if not merge_result.success:
            err_console.print(
                format_error(
                    f"Merge failed: {merge_result.error}",
                    suggestion=(
                        f"The branch '{branch_name}' exists in your local repo. "
                        "You can merge it manually with: "
                        f"git merge {branch_name}"
                    ),
                )
            )
            raise SystemExit(ExitCode.FAILURE)

        # Phase 3: clean up the temporary branch
        try:
            from maverick.runners.command import CommandRunner

            runner = CommandRunner(timeout=30.0)
            await runner.run(
                ["git", "branch", "-d", branch_name],
                cwd=repo_path,
            )
        except Exception:
            # Non-fatal — branch cleanup is best-effort
            logger.debug("branch_cleanup_failed", branch=branch_name)
    else:
        # No workspace — nothing to merge
        console.print("No workspace found — nothing to merge.")
        return

    console.print(format_success(f"Landed {len(commits)} commit(s) into local repo."))

    # Consolidate runway (best-effort, after merge, before teardown).
    # Runway data lives in the workspace (fly writes there), so pass
    # workspace cwd.  Fall back to user_repo when there's no workspace.
    repo_path_resolved = user_repo or Path.cwd().resolve()
    consolidation_cwd = cwd or repo_path_resolved
    await _maybe_consolidate(consolidation_cwd, no_consolidate, user_repo=repo_path_resolved)

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
    """Eject: push to a local preview branch and keep workspace."""
    from maverick.workspace.models import WorkspaceState

    preview_branch = branch or f"maverick/preview/{project_name}"

    if cwd is not None:
        from maverick.jj.client import JjClient
        from maverick.jj.errors import JjError

        client = JjClient(cwd=cwd)
        try:
            await client.bookmark_set(preview_branch, revision="@-")
            # Push from workspace → user repo (creates local branch only)
            await client.git_push(bookmark=preview_branch)
        except JjError as e:
            err_console.print(format_error(f"Eject push failed: {e}"))
            raise SystemExit(ExitCode.FAILURE) from e

        # Mark workspace as ejected (not deleted)
        manager.set_state(WorkspaceState.EJECTED)
    else:
        console.print(format_warning("No workspace found — nothing to eject."))
        return

    console.print(format_success(f"Ejected to local branch: {preview_branch}"))
    console.print(
        f"Run [bold]maverick land --finalize --branch {preview_branch}[/bold] "
        "when ready, or merge manually with [bold]git merge {preview_branch}[/bold]."
    )


# =====================================================================
# Finalize path
# =====================================================================


async def _finalize(
    base: str,
    branch: str | None,
    no_consolidate: bool = False,
) -> None:
    """Finalize after eject: merge preview branch into current branch, cleanup."""
    from maverick.library.actions.git import git_merge
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    project_name = user_repo.name
    preview_branch = branch or f"maverick/preview/{project_name}"

    manager = WorkspaceManager(user_repo_path=user_repo)

    console.print(f"Finalizing from branch [bold]{preview_branch}[/bold]...")

    # Merge preview branch into current branch
    merge_result = await git_merge(preview_branch, cwd=user_repo)
    if merge_result.success:
        console.print(format_success(f"Merged {preview_branch} into local repo."))
        # Clean up the preview branch
        try:
            from maverick.runners.command import CommandRunner

            runner = CommandRunner(timeout=30.0)
            await runner.run(
                ["git", "branch", "-d", preview_branch],
                cwd=user_repo,
            )
        except Exception:
            logger.debug("preview_branch_cleanup_failed", branch=preview_branch)

        # Consolidate runway (best-effort, after merge, before teardown).
        # Runway data lives in the workspace (fly writes there).
        consolidation_cwd = manager.workspace_path if manager.exists else user_repo
        await _maybe_consolidate(consolidation_cwd, no_consolidate, user_repo=user_repo)
    else:
        err_console.print(
            format_error(
                f"Merge failed: {merge_result.error}",
                suggestion=(f"You can merge manually with: git merge {preview_branch}"),
            )
        )
        raise SystemExit(ExitCode.FAILURE)
    if manager.exists:
        await manager.teardown()
        console.print("Workspace cleaned up.")
    else:
        console.print("No workspace to clean up.")


# =====================================================================
# Runway consolidation
# =====================================================================


async def _maybe_consolidate(
    runway_cwd: Path,
    no_consolidate: bool,
    *,
    user_repo: Path | None = None,
) -> None:
    """Best-effort runway consolidation after merge.

    Runs consolidation against ``runway_cwd`` (typically the workspace where
    fly wrote runway data).  When ``user_repo`` is provided and has an
    initialized runway, the consolidated semantic files are copied there so
    they survive workspace teardown.

    When the workspace is about to be torn down, consolidation is forced
    (threshold checks skipped) because the data will be lost otherwise.

    Args:
        runway_cwd: Directory containing ``.maverick/runway/`` with data.
        no_consolidate: If True, skip consolidation entirely.
        user_repo: User's repository path.  If set and its runway is
            initialized, semantic output is synced from workspace to
            user repo after consolidation.
    """
    if no_consolidate:
        return

    try:
        from maverick.config import load_config

        config = load_config()
        if not config.runway.enabled or not config.runway.consolidation.auto:
            return

        from maverick.library.actions.consolidation import consolidate_runway

        # Force consolidation when workspace data would be lost on teardown.
        force = user_repo is not None and runway_cwd != user_repo

        console.print("Consolidating runway knowledge store...")
        result = await consolidate_runway(
            cwd=runway_cwd,
            max_age_days=config.runway.consolidation.max_episodic_age_days,
            max_records=config.runway.consolidation.max_episodic_records,
            force=force,
        )
        if result.skipped:
            logger.debug("runway_consolidation_skipped", reason=result.skip_reason)
        elif result.success:
            msg = f"  Pruned {result.records_pruned} old records."
            if result.summary_updated:
                msg += " Updated consolidated-insights.md."
            console.print(msg)

            # Sync consolidated semantic files to user repo so they
            # survive workspace teardown.
            if user_repo is not None and runway_cwd != user_repo:
                _sync_runway_semantics(runway_cwd, user_repo)
        else:
            console.print(format_warning(f"Runway consolidation failed: {result.error}"))
    except Exception as exc:
        # Best-effort — never block landing
        console.print(format_warning(f"Runway consolidation failed: {exc}"))
        logger.debug("runway_consolidation_error", error=str(exc))


def _sync_runway_semantics(src_cwd: Path, dst_cwd: Path) -> None:
    """Copy runway data from workspace to user repo.

    Syncs semantic files (consolidated summaries), episodic files
    (pruned JSONL), and the index so data survives workspace teardown.
    Only copies if both runway directories exist.  Best-effort — errors
    are logged and swallowed.

    Args:
        src_cwd: Workspace directory with ``.maverick/runway/``.
        dst_cwd: User repo directory with ``.maverick/runway/``.
    """
    import shutil

    src_runway = src_cwd / ".maverick" / "runway"
    dst_runway = dst_cwd / ".maverick" / "runway"

    if not src_runway.is_dir():
        return
    if not dst_runway.is_dir():
        # User repo has no runway — nothing to sync into
        return

    try:
        # Sync each subdirectory (semantic/, episodic/) and index.json
        for subdir in ("semantic", "episodic"):
            src_dir = src_runway / subdir
            dst_dir = dst_runway / subdir
            if not src_dir.is_dir():
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            for src_file in src_dir.iterdir():
                if src_file.is_file():
                    shutil.copy2(src_file, dst_dir / src_file.name)

        # Sync index.json
        src_index = src_runway / "index.json"
        if src_index.is_file():
            shutil.copy2(src_index, dst_runway / "index.json")

        logger.debug(
            "runway_data_synced",
            src=str(src_runway),
            dst=str(dst_runway),
        )
    except Exception as exc:
        logger.debug("runway_sync_failed", error=str(exc))


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
        from maverick.executor import create_default_executor

        agent = CuratorAgent()
        _executor = create_default_executor()
        try:
            _result = await _executor.execute(
                step_name="curate",
                agent_name=agent.name,
                prompt={
                    "commits": curation_ctx["commits"],
                    "log_summary": curation_ctx["log_summary"],
                },
                cwd=cwd,
            )
            raw_output = str(_result.output) if _result.output else ""
        finally:
            await _executor.cleanup()
        plan = agent.parse_plan(raw_output)
    except SystemExit:
        raise
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
                    f"Executed {result['executed_count']}/{result['total_count']} steps.",
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


def _display_human_review_manifest(cwd: Path) -> None:
    """Display human review manifest if one exists from the fly phase."""
    import json as _json

    # Search for manifest in .maverick/plans/
    plans_dir = cwd / ".maverick" / "plans"
    if not plans_dir.is_dir():
        return

    manifest_path = plans_dir / "human-review-manifest.json"
    if not manifest_path.is_file():
        return

    try:
        items = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    if not items:
        return

    needs_review = [i for i in items if i.get("status") == "needs-human-review"]
    if not needs_review:
        console.print(format_success("All beads passed review cleanly."))
        return

    console.print()
    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Bead", width=20)
    table.add_column("Title", width=40)
    table.add_column("Key Findings")

    for item in needs_review:
        findings_str = (
            "\n".join(
                f"  - {f[:100]}..." if len(f) > 100 else f"  - {f}"
                for f in item.get("key_findings", [])
            )
            or "(no findings captured)"
        )
        table.add_row(
            item.get("bead_id", "?"),
            item.get("title", "?")[:40],
            findings_str,
        )

    panel = Panel(
        table,
        title=f"Human Review Required ({len(needs_review)} bead{'s' if len(needs_review) != 1 else ''})",  # noqa: E501
        border_style="yellow",
    )
    console.print(panel)
    console.print()
