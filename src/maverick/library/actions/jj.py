"""Jujutsu (jj) actions for workflow execution.

jj-specific operations that complement the standard git actions in git.py.
In colocated mode (.jj/ + .git/), plain git commands and jj commands
both see the same repository state.

These actions provide jj-only features used by the fly workflow:
- Operation snapshots and rollback for bead-loop safety
- WIP change descriptions for observability
- Post-hoc history curation (absorb, squash)

All functions accept an optional ``cwd`` parameter.  When omitted, the
current working directory is used (backward compatible).  When provided,
the underlying :class:`~maverick.jj.client.JjClient` targets that path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.logging import get_logger

logger = get_logger(__name__)


def _make_client(cwd: str | Path | None = None) -> JjClient:
    """Create a JjClient for the given (or current) working directory."""
    return JjClient(cwd=Path(cwd) if cwd else Path.cwd())


# =============================================================================
# Change description (label WIP changes for jj log visibility)
# =============================================================================


async def jj_describe(
    message: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Set the description of the current working-copy change.

    Unlike ``git_commit`` this does NOT finalise the change, so it
    stays editable.  Useful for labelling WIP changes at the start
    of a bead so ``jj log`` shows what is in-flight.

    Args:
        message: Description to set on the current change (``@``).
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if describe succeeded
        - error: Error message if failed, None otherwise
    """
    try:
        client = _make_client(cwd)
        await client.describe(message)
        return {"success": True, "error": None}
    except (JjError, OSError) as e:
        logger.debug("jj_describe_failed", error=str(e))
        return {"success": False, "error": str(e)}


# =============================================================================
# Operation log safety (snapshot / rollback)
# =============================================================================


async def jj_snapshot_operation(
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Capture the current jj operation ID for potential rollback.

    Args:
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if snapshot succeeded
        - operation_id: The current operation ID
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        result = await client.snapshot_operation()
        return {
            "success": True,
            "operation_id": result.operation_id,
            "error": None,
        }
    except (JjError, OSError) as e:
        logger.debug("jj_snapshot_failed", error=str(e))
        return {
            "success": False,
            "operation_id": None,
            "error": str(e),
        }


async def jj_restore_operation(
    operation_id: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Restore the repository to a previous operation state.

    In colocated mode this rewinds both jj and git state.

    Args:
        operation_id: Operation ID from jj_snapshot_operation.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if restore succeeded
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        await client.restore_operation(operation_id)
        return {"success": True, "error": None}
    except (JjError, OSError) as e:
        logger.debug("jj_restore_failed", error=str(e))
        return {"success": False, "error": str(e)}


# =============================================================================
# Post-hoc curation
# =============================================================================


async def jj_squash(
    into: str = "@-",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Squash the current change into its parent (or specified revision).

    Args:
        into: Revision to squash into (default: parent ``@-``).
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if squash succeeded
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        target = into if into != "@-" else None
        await client.squash(into=target)
        return {"success": True, "error": None}
    except (JjError, OSError) as e:
        logger.debug("jj_squash_failed", error=str(e))
        return {"success": False, "error": str(e)}


async def jj_absorb(cwd: Path | None = None) -> dict[str, Any]:
    """Absorb working-copy changes into relevant ancestor commits.

    Args:
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if absorb succeeded
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        await client.absorb()
        return {"success": True, "error": None}
    except (JjError, OSError) as e:
        logger.debug("jj_absorb_failed", error=str(e))
        return {"success": False, "error": str(e)}


async def jj_log(
    revset: str = "@",
    limit: int = 10,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Show jj log for a revset.

    Args:
        revset: Revset expression (default: ``@``).
        limit: Maximum number of entries (default: 10).
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if log succeeded
        - output: Log output text
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        result = await client.log(revset=revset, limit=limit)
        return {
            "success": True,
            "output": result.output,
            "error": None,
        }
    except (JjError, OSError) as e:
        logger.debug("jj_log_failed", error=str(e))
        return {"success": False, "output": "", "error": str(e)}


async def jj_diff(
    revision: str = "@",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Show diff for a revision in git format.

    Args:
        revision: Revision to diff (default: ``@``).
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if diff succeeded
        - output: Diff output text
        - error: Error message if failed
    """
    try:
        client = _make_client(cwd)
        result = await client.diff(revision=revision)
        return {
            "success": True,
            "output": result.output,
            "error": None,
        }
    except (JjError, OSError) as e:
        logger.debug("jj_diff_failed", error=str(e))
        return {"success": False, "output": "", "error": str(e)}


# =============================================================================
# Bead commit (workspace mode)
# =============================================================================


async def jj_commit_bead(
    message: str,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Finalise the current change and start a fresh one.

    In jj there is no staging area.  A "commit" is:
    1. ``jj describe -m <message>``  — set the change description.
    2. ``jj new``                    — start a new empty change.

    This replaces ``git_commit`` when operating in a jj-only workspace.

    Args:
        message: Description for the current change.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if commit succeeded
        - message: The commit message used
        - error: Error message if failed
    """
    try:
        client = _make_client(Path(cwd) if cwd else None)
        await client.describe(message)
        new_result = await client.new()
        return {
            "success": True,
            "message": message,
            "change_id": new_result.change_id,
            "error": None,
        }
    except (JjError, OSError) as e:
        logger.debug("jj_commit_bead_failed", error=str(e))
        return {
            "success": False,
            "message": message,
            "change_id": None,
            "error": str(e),
        }


# =============================================================================
# History curation (post-loop)
# =============================================================================

# Keywords that identify fix/cleanup commits eligible for squashing
_FIX_KEYWORD_RE = ("fix", "fixup", "lint", "format", "typecheck")


async def curate_history(
    base_revision: str = "main",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Reorganize bead commits into cleaner history before push.

    Runs two passes:
    1. ``jj absorb`` — mechanically distributes stray hunks into the
       ancestor commits they logically belong to.
    2. Heuristic squash — any commit whose description contains fix/fixup
       keywords gets squashed into its parent via ``jj squash``.

    This is intentionally conservative.  An agent-driven curator can do
    smarter splits/reorders later (see GitHub enhancement issue).

    Args:
        base_revision: Revision marking the start of the work.
            Only commits *after* this are candidates for curation.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if curation completed (partial failures are logged)
        - absorb_ran: True if absorb executed successfully
        - squashed_count: Number of commits squashed into parents
        - error: Error message if a fatal error occurred
    """
    squashed_count = 0
    absorb_ran = False
    client = _make_client(cwd)

    try:
        # --- Pass 1: jj absorb ------------------------------------------
        try:
            await client.absorb()
            absorb_ran = True
            logger.info("curate_history: absorb completed")
        except JjError as e:
            # absorb failing is non-fatal (e.g. nothing to absorb)
            logger.debug(
                "curate_history: absorb skipped",
                error=str(e),
            )

        # --- Pass 2: heuristic squash of fix beads ----------------------
        revset = f"{base_revision}..@-"
        try:
            log_result = await client.log(revset=revset, limit=1000)
        except JjError:
            # If the revset is empty or invalid, just skip squashing
            logger.debug("curate_history: log revset produced no results")
            return {
                "success": True,
                "absorb_ran": absorb_ran,
                "squashed_count": 0,
                "error": None,
            }

        # The structured log gives us change entries
        changes = log_result.changes
        if not changes:
            return {
                "success": True,
                "absorb_ran": absorb_ran,
                "squashed_count": 0,
                "error": None,
            }

        # Walk from newest to oldest so squashing doesn't invalidate
        # earlier change IDs (jj rewrites descendants).
        for change in changes:
            description_lower = change.description.lower()
            is_fix = any(kw in description_lower for kw in _FIX_KEYWORD_RE)
            if not is_fix:
                continue

            try:
                await client.squash(revision=change.change_id)
                squashed_count += 1
                logger.info(
                    "curate_history: squashed fix commit",
                    change_id=change.change_id,
                    description=change.description[:60],
                )
            except JjError:
                logger.debug(
                    "curate_history: squash skipped",
                    change_id=change.change_id,
                )

        return {
            "success": True,
            "absorb_ran": absorb_ran,
            "squashed_count": squashed_count,
            "error": None,
        }

    except (JjError, OSError) as e:
        logger.debug("curate_history_failed", error=str(e))
        return {
            "success": False,
            "absorb_ran": absorb_ran,
            "squashed_count": squashed_count,
            "error": str(e),
        }


# =============================================================================
# Agentic curation helpers (used by ``maverick land``)
# =============================================================================


async def gather_curation_context(
    base_revision: str = "main",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Gather commit log and per-commit stats for curation.

    Collects ``jj log --stat`` and per-commit ``jj diff --stat`` for each
    commit between *base_revision* and the current working copy.

    Args:
        base_revision: Revision marking the start of the work.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: bool
        - commits: list of {change_id, description, stats}
        - log_summary: Full ``jj log --stat`` output
        - error: str | None
    """
    revset = f"{base_revision}..@-"
    client = _make_client(cwd)

    try:
        # 1. Get commit list via structured log
        try:
            log_result = await client.log(revset=revset, limit=1000)
        except JjError as e:
            # Log the actual error — silently returning empty can mask bugs
            logger.warning(
                "gather_curation_no_commits",
                revset=revset,
                cwd=str(cwd),
                error=str(e),
            )
            return {
                "success": True,
                "commits": [],
                "log_summary": "",
                "error": None,
            }

        if not log_result.changes:
            return {
                "success": True,
                "commits": [],
                "log_summary": "",
                "error": None,
            }

        # 2. Get summary log with file stats
        try:
            stat_result = await client.diff_stat(revision="@-", from_rev=base_revision)
            log_summary = stat_result.output
        except JjError:
            log_summary = ""

        # 3. Per-commit stats
        commits: list[dict[str, str]] = []
        for change in log_result.changes:
            try:
                stat = await client.diff_stat(revision=change.change_id)
                stats = stat.output
            except JjError:
                stats = ""

            commits.append(
                {
                    "change_id": change.change_id,
                    "description": change.description,
                    "stats": stats,
                }
            )

        logger.info(
            "gather_curation_context: collected commits",
            count=len(commits),
        )
        return {
            "success": True,
            "commits": commits,
            "log_summary": log_summary,
            "error": None,
        }

    except (JjError, OSError) as e:
        logger.debug("gather_curation_context_failed", error=str(e))
        return {
            "success": False,
            "commits": [],
            "log_summary": "",
            "error": str(e),
        }


async def execute_curation_plan(
    plan: list[dict[str, Any]],
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Execute a curation plan (list of jj commands) with rollback safety.

    Takes a jj operation snapshot before starting.  On any failure,
    restores to the snapshot.

    Args:
        plan: List of plan steps, each with:
            - command: jj subcommand (``"squash"``, ``"describe"``, ``"rebase"``)
            - args: list of argument strings
            - reason: human-readable explanation
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: bool
        - executed_count: int
        - total_count: int
        - snapshot_id: operation ID for manual recovery
        - error: str | None
    """
    total_count = len(plan)
    if total_count == 0:
        return {
            "success": True,
            "executed_count": 0,
            "total_count": 0,
            "snapshot_id": None,
            "error": None,
        }

    # Snapshot for rollback
    snapshot = await jj_snapshot_operation(cwd=cwd)
    if not snapshot["success"]:
        return {
            "success": False,
            "executed_count": 0,
            "total_count": total_count,
            "snapshot_id": None,
            "error": f"Failed to create snapshot: {snapshot['error']}",
        }
    snapshot_id = snapshot["operation_id"]

    client = _make_client(cwd)
    executed_count = 0
    try:
        for step in plan:
            command = step.get("command", "")
            args = step.get("args", [])
            reason = step.get("reason", "")

            cmd: list[str] = ["jj", command, *args]
            logger.info(
                "execute_curation_plan: running step",
                command=command,
                reason=reason[:80],
            )

            result = await client._runner.run(cmd, cwd=client.cwd)
            if not result.success:
                error_msg = (
                    f"Step {executed_count + 1}/{total_count} failed: "
                    f"jj {command} {' '.join(args)}: "
                    f"{result.stderr.strip()}"
                )
                logger.debug(error_msg)

                # Rollback
                await jj_restore_operation(snapshot_id, cwd=cwd)
                return {
                    "success": False,
                    "executed_count": executed_count,
                    "total_count": total_count,
                    "snapshot_id": snapshot_id,
                    "error": error_msg,
                }

            executed_count += 1

        logger.info(
            "execute_curation_plan: completed",
            executed_count=executed_count,
            total_count=total_count,
        )
        return {
            "success": True,
            "executed_count": executed_count,
            "total_count": total_count,
            "snapshot_id": snapshot_id,
            "error": None,
        }

    except (JjError, OSError) as e:
        logger.debug("execute_curation_plan_failed", error=str(e))
        # Attempt rollback
        await jj_restore_operation(snapshot_id, cwd=cwd)
        return {
            "success": False,
            "executed_count": executed_count,
            "total_count": total_count,
            "snapshot_id": snapshot_id,
            "error": str(e),
        }
