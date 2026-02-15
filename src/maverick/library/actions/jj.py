"""Jujutsu (jj) actions for workflow execution.

jj-specific operations that complement the standard git actions in git.py.
In colocated mode (.jj/ + .git/), plain git commands and jj commands
both see the same repository state.

These actions provide jj-only features used by the fly workflow:
- Operation snapshots and rollback for bead-loop safety
- WIP change descriptions for observability
- Post-hoc history curation (absorb, squash)
"""

from __future__ import annotations

import asyncio
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Change description (label WIP changes for jj log visibility)
# =============================================================================


async def jj_describe(message: str) -> dict[str, Any]:
    """Set the description of the current working-copy change.

    Unlike ``git_commit`` this does NOT finalise the change, so it
    stays editable.  Useful for labelling WIP changes at the start
    of a bead so ``jj log`` shows what is in-flight.

    Args:
        message: Description to set on the current change (``@``).

    Returns:
        Dict with:
        - success: True if describe succeeded
        - error: Error message if failed, None otherwise
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "describe",
            "-m",
            message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj describe failed: {stderr.decode()}")

        logger.debug("Described current change", message=message[:80])
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.error(f"jj describe failed: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Operation log safety (snapshot / rollback)
# =============================================================================


async def jj_snapshot_operation() -> dict[str, Any]:
    """Capture the current jj operation ID for potential rollback.

    Returns:
        Dict with:
        - success: True if snapshot succeeded
        - operation_id: The current operation ID
        - error: Error message if failed
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "op",
            "log",
            "--no-graph",
            "-T",
            'self.id() ++ "\n"',
            "--limit",
            "1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj op log failed: {stderr.decode()}")

        operation_id = stdout.decode().strip().split("\n")[0]
        logger.debug("Captured jj operation snapshot", operation_id=operation_id)

        return {
            "success": True,
            "operation_id": operation_id,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj snapshot failed: {e}")
        return {
            "success": False,
            "operation_id": None,
            "error": str(e),
        }


async def jj_restore_operation(operation_id: str) -> dict[str, Any]:
    """Restore the repository to a previous operation state.

    In colocated mode this rewinds both jj and git state.

    Args:
        operation_id: Operation ID from jj_snapshot_operation.

    Returns:
        Dict with:
        - success: True if restore succeeded
        - error: Error message if failed
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "op",
            "restore",
            operation_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj op restore failed: {stderr.decode()}")

        logger.info("Restored jj operation", operation_id=operation_id)
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.error(f"jj op restore failed: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Post-hoc curation
# =============================================================================


async def jj_squash(into: str = "@-") -> dict[str, Any]:
    """Squash the current change into its parent (or specified revision).

    Args:
        into: Revision to squash into (default: parent ``@-``).

    Returns:
        Dict with:
        - success: True if squash succeeded
        - error: Error message if failed
    """
    try:
        cmd = ["jj", "squash"]
        if into != "@-":
            cmd.extend(["--into", into])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj squash failed: {stderr.decode()}")

        logger.debug("Squashed change", into=into)
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.error(f"jj squash failed: {e}")
        return {"success": False, "error": str(e)}


async def jj_absorb() -> dict[str, Any]:
    """Absorb working-copy changes into relevant ancestor commits.

    Returns:
        Dict with:
        - success: True if absorb succeeded
        - error: Error message if failed
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "absorb",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj absorb failed: {stderr.decode()}")

        logger.debug("Absorbed changes into ancestors")
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.error(f"jj absorb failed: {e}")
        return {"success": False, "error": str(e)}


async def jj_log(revset: str = "@", limit: int = 10) -> dict[str, Any]:
    """Show jj log for a revset.

    Args:
        revset: Revset expression (default: ``@``).
        limit: Maximum number of entries (default: 10).

    Returns:
        Dict with:
        - success: True if log succeeded
        - output: Log output text
        - error: Error message if failed
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            revset,
            "--limit",
            str(limit),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj log failed: {stderr.decode()}")

        return {
            "success": True,
            "output": stdout.decode(),
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj log failed: {e}")
        return {"success": False, "output": "", "error": str(e)}


async def jj_diff(revision: str = "@") -> dict[str, Any]:
    """Show diff for a revision in git format.

    Args:
        revision: Revision to diff (default: ``@``).

    Returns:
        Dict with:
        - success: True if diff succeeded
        - output: Diff output text
        - error: Error message if failed
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "diff",
            "-r",
            revision,
            "--git",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj diff failed: {stderr.decode()}")

        return {
            "success": True,
            "output": stdout.decode(),
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj diff failed: {e}")
        return {"success": False, "output": "", "error": str(e)}


# =============================================================================
# History curation (post-loop)
# =============================================================================

# Keywords that identify fix/cleanup commits eligible for squashing
_FIX_KEYWORD_RE = ("fix", "fixup", "lint", "format", "typecheck")


async def curate_history(
    base_revision: str = "main",
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

    Returns:
        Dict with:
        - success: True if curation completed (partial failures are logged)
        - absorb_ran: True if absorb executed successfully
        - squashed_count: Number of commits squashed into parents
        - error: Error message if a fatal error occurred
    """
    squashed_count = 0
    absorb_ran = False

    try:
        # --- Pass 1: jj absorb ------------------------------------------
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "absorb",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            absorb_ran = True
            logger.info("curate_history: absorb completed")
        else:
            # absorb failing is non-fatal (e.g. nothing to absorb)
            logger.debug(
                "curate_history: absorb skipped",
                stderr=stderr.decode().strip(),
            )

        # --- Pass 2: heuristic squash of fix beads ----------------------
        # Get the list of commits between base and @ (exclusive of @
        # which is the empty working-copy change).
        revset = f"{base_revision}..@-"
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            revset,
            "--no-graph",
            "-T",
            'change_id ++ "\\t" ++ description.first_line() ++ "\\n"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            # If the revset is empty or invalid, just skip squashing
            logger.debug(
                "curate_history: log revset produced no results",
                stderr=stderr.decode().strip(),
            )
            return {
                "success": True,
                "absorb_ran": absorb_ran,
                "squashed_count": 0,
                "error": None,
            }

        # Parse commits (oldest first — jj log outputs newest first)
        lines = [ln for ln in stdout.decode().strip().splitlines() if "\t" in ln]
        lines.reverse()  # oldest → newest

        # Walk from newest to oldest so squashing doesn't invalidate
        # earlier change IDs (jj rewrites descendants).
        for line in reversed(lines):
            change_id, description = line.split("\t", 1)
            description_lower = description.lower()

            is_fix = any(kw in description_lower for kw in _FIX_KEYWORD_RE)
            if not is_fix:
                continue

            # Squash this fix commit into its parent
            proc = await asyncio.create_subprocess_exec(
                "jj",
                "squash",
                "-r",
                change_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, sq_stderr = await proc.communicate()
            if proc.returncode == 0:
                squashed_count += 1
                logger.info(
                    "curate_history: squashed fix commit",
                    change_id=change_id,
                    description=description[:60],
                )
            else:
                logger.debug(
                    "curate_history: squash skipped",
                    change_id=change_id,
                    stderr=sq_stderr.decode().strip(),
                )

        return {
            "success": True,
            "absorb_ran": absorb_ran,
            "squashed_count": squashed_count,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"curate_history failed: {e}")
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
) -> dict[str, Any]:
    """Gather commit log and per-commit stats for curation.

    Collects ``jj log --stat`` and per-commit ``jj diff --stat`` for each
    commit between *base_revision* and the current working copy.

    Args:
        base_revision: Revision marking the start of the work.

    Returns:
        Dict with:
        - success: bool
        - commits: list of {change_id, description, stats}
        - log_summary: Full ``jj log --stat`` output
        - error: str | None
    """
    revset = f"{base_revision}..@-"

    try:
        # 1. Get commit list (change_id + first-line description)
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            revset,
            "--no-graph",
            "-T",
            'change_id ++ "\\t" ++ description.first_line() ++ "\\n"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            # Empty revset — no commits to curate
            return {
                "success": True,
                "commits": [],
                "log_summary": "",
                "error": None,
            }

        lines = [ln for ln in stdout.decode().strip().splitlines() if "\t" in ln]
        if not lines:
            return {
                "success": True,
                "commits": [],
                "log_summary": "",
                "error": None,
            }

        # 2. Get summary log with file stats
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            revset,
            "--stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        log_stdout, _ = await proc.communicate()
        log_summary = log_stdout.decode() if proc.returncode == 0 else ""

        # 3. Per-commit stats
        commits: list[dict[str, str]] = []
        for line in lines:
            change_id, description = line.split("\t", 1)
            # Get per-commit diff stats (not full diffs — keeps context small)
            proc = await asyncio.create_subprocess_exec(
                "jj",
                "diff",
                "-r",
                change_id,
                "--stat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stat_stdout, _ = await proc.communicate()
            stats = stat_stdout.decode() if proc.returncode == 0 else ""

            commits.append(
                {
                    "change_id": change_id,
                    "description": description,
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

    except (RuntimeError, OSError) as e:
        logger.error(f"gather_curation_context failed: {e}")
        return {
            "success": False,
            "commits": [],
            "log_summary": "",
            "error": str(e),
        }


async def execute_curation_plan(
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute a curation plan (list of jj commands) with rollback safety.

    Takes a jj operation snapshot before starting.  On any failure,
    restores to the snapshot.

    Args:
        plan: List of plan steps, each with:
            - command: jj subcommand (``"squash"``, ``"describe"``, ``"rebase"``)
            - args: list of argument strings
            - reason: human-readable explanation

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
    snapshot = await jj_snapshot_operation()
    if not snapshot["success"]:
        return {
            "success": False,
            "executed_count": 0,
            "total_count": total_count,
            "snapshot_id": None,
            "error": f"Failed to create snapshot: {snapshot['error']}",
        }
    snapshot_id = snapshot["operation_id"]

    executed_count = 0
    try:
        for step in plan:
            command = step.get("command", "")
            args = step.get("args", [])
            reason = step.get("reason", "")

            cmd = ["jj", command, *args]
            logger.info(
                "execute_curation_plan: running step",
                command=command,
                reason=reason[:80],
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = (
                    f"Step {executed_count + 1}/{total_count} failed: "
                    f"jj {command} {' '.join(args)}: {stderr.decode().strip()}"
                )
                logger.error(error_msg)

                # Rollback
                await jj_restore_operation(snapshot_id)
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

    except (RuntimeError, OSError) as e:
        logger.error(f"execute_curation_plan failed: {e}")
        # Attempt rollback
        await jj_restore_operation(snapshot_id)
        return {
            "success": False,
            "executed_count": executed_count,
            "total_count": total_count,
            "snapshot_id": snapshot_id,
            "error": str(e),
        }
