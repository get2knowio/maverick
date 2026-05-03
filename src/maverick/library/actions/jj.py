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
from typing import TYPE_CHECKING, Any

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.library.actions.git_models import SnapshotResult

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

    In jj there is no staging area. ``jj commit -m <msg>`` finalizes the
    working-copy change with the given description and creates a fresh
    empty change on top — the jj-native equivalent of ``git commit``.

    The returned ``change_id`` is the **finalized** change (the one the
    bead's work just landed on), not the new empty WIP — i.e. the SHA
    the supervisor surfaces in the "bead complete (xxx)" status line.

    Args:
        message: Description for the current change.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        Dict with:
        - success: True if commit succeeded
        - message: The commit message used
        - change_id: Stable change ID of the finalized change (or None)
        - error: Error message if failed
    """
    try:
        client = _make_client(Path(cwd) if cwd else None)
        commit_result = await client.commit(message)
        return {
            "success": True,
            "message": message,
            "change_id": commit_result.change_id or None,
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


async def commit_bead_changes(
    message: str,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Finalise the bead's changes using whichever VCS the cwd has.

    Dispatches to :func:`jj_commit_bead` when ``.jj/`` is found in or
    above ``cwd``; otherwise runs ``git add -A && git commit -m <msg>``
    against the user's plain-git checkout. Either way, the bead's edits
    end up as a commit on the current branch.

    Earlier revisions called :func:`jj_commit_bead` straight through. On
    a plain-git user repo (the sample-maverick-project case, and any
    non-colocated maverick project) the underlying ``jj commit`` fails
    because there is no jj repo to talk to — the e2e on
    ``005-e2e-cross-provider`` saw "Commit failed for ...:" with an
    empty error message at the end of an otherwise green bead. This
    helper is the same shape as :func:`snapshot_uncommitted_changes`:
    one place that detects the VCS, two well-tested paths.

    Returns the same dict shape as :func:`jj_commit_bead` so callers
    can stay vcs-agnostic. ``change_id`` carries the jj change-id on
    the jj path and the git HEAD sha on the plain-git path — both are
    stable commit identifiers.
    """
    target = Path(cwd) if cwd is not None else Path.cwd()
    target = target.resolve()

    if _is_jj_repo(target):
        return await jj_commit_bead(message, cwd=target)

    # Plain-git path.
    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=target)
    try:
        add = await runner.run(["git", "add", "-A"], cwd=target)
        if not add.success:
            return {
                "success": False,
                "message": message,
                "change_id": None,
                "error": (f"git add failed: {add.stderr.strip() or 'non-zero exit'}"),
            }
        commit = await runner.run(
            ["git", "commit", "-m", message],
            cwd=target,
        )
    except OSError as exc:
        return {
            "success": False,
            "message": message,
            "change_id": None,
            "error": f"git commit failed: {exc}",
        }

    if not commit.success:
        # ``git commit`` on a clean tree exits non-zero with "nothing to
        # commit" — surface that as a soft failure (not a crash).
        stderr = commit.stderr.strip() or commit.stdout.strip() or "non-zero exit"
        return {
            "success": False,
            "message": message,
            "change_id": None,
            "error": f"git commit failed: {stderr}",
        }

    sha: str | None = None
    try:
        rev = await runner.run(["git", "rev-parse", "HEAD"], cwd=target)
        if rev.success:
            sha = rev.stdout.strip() or None
    except OSError:
        pass

    return {
        "success": True,
        "message": message,
        "change_id": sha,
        "error": None,
    }


# =============================================================================
# Snapshot uncommitted changes (jj-native replacement for git_commit path)
# =============================================================================

#: Threshold above which a snapshot commit gets a "large snapshot" warning
#: appended to its description so the curator can flag it during land.
_SNAPSHOT_FILE_THRESHOLD: int = 10


async def jj_snapshot_changes(
    message: str = "chore: snapshot uncommitted changes",
    cwd: str | Path | None = None,
) -> SnapshotResult:
    """Commit any uncommitted changes via jj.

    The jj-native replacement for ``snapshot_uncommitted_changes``. In jj
    every command auto-snapshots the working copy, so this just needs to
    finalize the current change and start a fresh one — which is exactly
    what :meth:`JjClient.commit` does. Operates correctly in colocated
    mode (jj's op log records the snapshot, keeping git in sync).

    When the snapshot exceeds ``_SNAPSHOT_FILE_THRESHOLD`` files, a
    warning string with diff stats is returned in
    :attr:`SnapshotResult.warning` so the curator can flag the snapshot
    during land.

    Args:
        message: Description for the snapshot change.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        :class:`SnapshotResult`. ``committed=False`` when there were no
        changes to snapshot. ``commit_sha`` carries the jj change ID
        (not a git SHA — but still a stable commit identifier).
    """
    from maverick.library.actions.git_models import SnapshotDiffStats, SnapshotResult

    client = _make_client(cwd)

    # Detect uncommitted changes via jj diff_stat. An empty working copy
    # has zero files changed.
    try:
        stat = await client.diff_stat(revision="@")
    except JjError as e:
        logger.debug("jj_snapshot_diff_stat_failed", error=str(e))
        return SnapshotResult(
            success=False,
            committed=False,
            error=f"jj diff --stat failed: {e}",
        )

    if stat.files_changed == 0:
        return SnapshotResult(success=True, committed=False)

    diff_stats = SnapshotDiffStats(
        file_count=stat.files_changed,
        insertions=stat.insertions,
        deletions=stat.deletions,
        files=(),
    )

    warning: str | None = None
    effective_message = message
    if stat.files_changed > _SNAPSHOT_FILE_THRESHOLD:
        warning = (
            f"Large snapshot: {stat.files_changed} files, "
            f"+{stat.insertions}/-{stat.deletions} lines. "
            "Review before merging — may contain unrelated changes."
        )
        effective_message = f"{message}\n\nWARNING: {warning}\n"

    try:
        commit_result = await client.commit(effective_message)
    except JjError as e:
        logger.debug("jj_snapshot_commit_failed", error=str(e))
        return SnapshotResult(
            success=False,
            committed=False,
            diff_stats=diff_stats,
            warning=warning,
            error=f"jj commit failed: {e}",
        )

    return SnapshotResult(
        success=True,
        committed=True,
        commit_sha=commit_result.change_id or None,
        diff_stats=diff_stats,
        warning=warning,
    )


def _is_jj_repo(cwd: Path) -> bool:
    """Return True when ``cwd`` is a jj repo (or jj-colocated git repo).

    Cheap directory probe — no subprocess. The full ``jj root`` invocation
    would be more authoritative but is overkill for a cwd-vs-vcs decision.
    Walks up the tree the way jj does itself, so a subdirectory of a jj
    repo still resolves correctly.
    """
    candidate = cwd
    for _ in range(64):  # bound to defend against pathological symlink loops
        if (candidate / ".jj").is_dir():
            return True
        parent = candidate.parent
        if parent == candidate:
            return False
        candidate = parent
    return False


async def snapshot_uncommitted_changes(
    message: str = "chore: snapshot uncommitted changes",
    cwd: str | Path | None = None,
) -> SnapshotResult:
    """Snapshot uncommitted changes using whichever VCS the cwd has.

    Wraps :func:`jj_snapshot_changes` (when ``.jj/`` is found in or
    above ``cwd``) or a plain-git ``git add -A && git commit`` path
    (otherwise). Either way, the working copy ends up clean and the
    returned :class:`SnapshotResult` describes whether anything was
    committed.

    The detection is intentionally one-place — earlier revisions wired
    ``jj diff --stat`` directly into the fly workflow, which crashed on
    plain-git user repos. New maverick-managed repos are typically jj-
    colocated; the sample-maverick-project fixture and many fresh
    setups are not.

    Args:
        message: Commit description for the snapshot.
        cwd: Working directory. Defaults to ``Path.cwd()``.

    Returns:
        :class:`SnapshotResult`. ``committed=False`` when the working
        copy was already clean.
    """
    from maverick.library.actions.git_models import SnapshotResult
    from maverick.runners.command import CommandRunner

    target = Path(cwd) if cwd is not None else Path.cwd()
    target = target.resolve()

    if _is_jj_repo(target):
        return await jj_snapshot_changes(message=message, cwd=target)

    # Plain-git path: status check + git add -A && git commit.
    runner = CommandRunner(cwd=target)
    try:
        status = await runner.run(["git", "status", "--porcelain"], cwd=target)
    except OSError as exc:
        return SnapshotResult(
            success=False,
            committed=False,
            error=f"git status failed: {exc}",
        )

    if not status.success:
        return SnapshotResult(
            success=False,
            committed=False,
            error=f"git status failed: {status.stderr.strip() or 'non-zero exit'}",
        )

    if not status.stdout.strip():
        return SnapshotResult(success=True, committed=False)

    try:
        add = await runner.run(["git", "add", "-A"], cwd=target)
        if not add.success:
            return SnapshotResult(
                success=False,
                committed=False,
                error=f"git add failed: {add.stderr.strip() or 'non-zero exit'}",
            )
        commit = await runner.run(
            ["git", "commit", "-m", message],
            cwd=target,
        )
    except OSError as exc:
        return SnapshotResult(
            success=False,
            committed=False,
            error=f"git commit failed: {exc}",
        )

    if not commit.success:
        return SnapshotResult(
            success=False,
            committed=False,
            error=f"git commit failed: {commit.stderr.strip() or 'non-zero exit'}",
        )

    # Resolve the new HEAD sha for parity with jj_snapshot_changes (which
    # returns a change-id).
    sha: str | None = None
    try:
        rev = await runner.run(["git", "rev-parse", "HEAD"], cwd=target)
        if rev.success:
            sha = rev.stdout.strip() or None
    except OSError:
        pass

    return SnapshotResult(
        success=True,
        committed=True,
        commit_sha=sha,
    )


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
                stderr = result.stderr.strip()

                # Skip steps targeting immutable commits rather than
                # aborting the entire plan.  The curator agent sometimes
                # proposes operations on commits that are already on main
                # (e.g., squashing a workspace config tweak into the
                # snapshot commit).  These are safe to skip.
                if "is immutable" in stderr or "immutable commits" in stderr:
                    logger.info(
                        "execute_curation_plan: skipping immutable step",
                        step=executed_count + 1,
                        command=command,
                        reason=reason[:80],
                    )
                    executed_count += 1
                    continue

                error_msg = (
                    f"Step {executed_count + 1}/{total_count} failed: "
                    f"jj {command} {' '.join(args)}: {stderr}"
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
