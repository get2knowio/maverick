"""Jujutsu (jj) actions for workflow execution.

All write-path git operations use the jj CLI in colocated mode.
Read-only operations (GitPython, MCP tools) continue using .git directly.
Action names match the original git.py so YAML workflows need no changes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Tier 1 — Drop-in replacements (same action names as git.py)
# =============================================================================


async def git_has_changes() -> dict[str, Any]:
    """Check if there are uncommitted changes in the working copy.

    Uses ``jj diff --stat`` to detect any modifications.  Jujutsu has no
    staging area so ``has_staged`` is always ``False``.

    Returns:
        Dict with:
        - has_staged: Always False (jj has no index)
        - has_unstaged: True if working copy has modifications
        - has_untracked: True if working copy has modifications (same as unstaged)
        - has_any: True if any changes exist
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "diff",
            "--stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        has_any = bool(output)

        logger.debug(
            "jj change status",
            has_any=has_any,
            diff_stat_lines=len(output.splitlines()) if output else 0,
        )

        return {
            "has_staged": False,
            "has_unstaged": has_any,
            "has_untracked": has_any,
            "has_any": has_any,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj diff --stat failed: {e}")
        return {
            "has_staged": True,
            "has_unstaged": True,
            "has_untracked": True,
            "has_any": True,
        }


async def git_check_and_stage() -> dict[str, Any]:
    """Check for changes (staging is a no-op with jj).

    Returns:
        Dict with change status fields (same shape as git_has_changes).
    """
    return await git_has_changes()


async def git_add(
    paths: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Track specific paths (no-op unless force=True).

    Jujutsu auto-tracks all files in the working copy.  When ``force=True``
    we use ``jj file track`` to explicitly track otherwise-ignored paths.

    Args:
        paths: File paths to track. Ignored when force is False.
        force: Use ``jj file track`` to override ignore rules.

    Returns:
        Dict with:
        - success: True if operation succeeded
        - error: Error message if failed, None otherwise
    """
    if not force:
        logger.debug("git_add: no-op (jj auto-tracks)")
        return {"success": True, "error": None}

    if not paths:
        paths = ["."]

    try:
        cmd = ["jj", "file", "track", *paths]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj file track failed: {stderr.decode()}")

        logger.debug("Tracked paths via jj", paths=paths)
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.error(f"jj file track failed: {e}")
        return {"success": False, "error": str(e)}


async def git_stage_all() -> dict[str, Any]:
    """No-op: jj automatically tracks all working-copy changes.

    Returns:
        Dict with:
        - success: Always True
        - error: Always None
    """
    logger.debug("git_stage_all: no-op (jj auto-tracks)")
    return {"success": True, "error": None}


async def git_commit(
    message: str,
    add_all: bool = True,
    include_attribution: bool = True,
) -> dict[str, Any]:
    """Create a jj commit (describe + new).

    Workflow:
    1. Check ``jj diff --stat`` — if empty, return nothing_to_commit.
    2. Build full message (with optional attribution).
    3. ``jj describe -m <msg>`` — sets the current change description.
    4. ``jj new`` — starts a new empty change on top.
    5. Get commit SHA via ``jj log -r @- --no-graph -T 'commit_id ++ "\\n"'``.
    6. Get files via ``jj diff -r @- --summary``.

    Args:
        message: Commit message.
        add_all: Ignored (jj auto-tracks).
        include_attribution: Include AI co-author attribution.

    Returns:
        GitCommitResult as dict.
    """
    try:
        # 1. Check for changes
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "diff",
            "--stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if not stdout.decode().strip():
            return {
                "success": True,
                "commit_sha": None,
                "files_committed": [],
                "message": message,
                "nothing_to_commit": True,
            }

        # 2. Build full message
        full_message = message
        if include_attribution:
            attribution = (
                "\n\n🤖 Generated with Claude Code\n\n"
                "Co-Authored-By: Claude <noreply@anthropic.com>"
            )
            full_message += attribution

        # 3. Describe the current change
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "describe",
            "-m",
            full_message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj describe failed: {stderr.decode()}")

        # 4. Start a new change
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "new",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj new failed: {stderr.decode()}")

        # 5. Get commit SHA of the just-committed change (@-)
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            "@-",
            "--no-graph",
            "-T",
            'commit_id ++ "\n"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj log failed: {stderr.decode()}")
        commit_sha = stdout.decode().strip().split("\n")[0]

        # 6. Get list of files changed in that commit
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "diff",
            "-r",
            "@-",
            "--summary",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        raw_lines = (
            stdout.decode().strip().split("\n") if stdout.decode().strip() else []
        )
        # jj diff --summary outputs lines like "M src/file.py" or "A new_file.py"
        files_committed = tuple(
            line.split(None, 1)[1] for line in raw_lines if line and " " in line
        )

        return {
            "success": True,
            "commit_sha": commit_sha,
            "message": message,
            "files_committed": files_committed,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj commit failed: {e}")
        return {
            "success": False,
            "commit_sha": None,
            "message": message,
            "files_committed": (),
            "error": str(e),
        }


async def git_push(set_upstream: bool = True) -> dict[str, Any]:
    """Push current bookmark to remote via jj.

    Workflow:
    1. Get bookmark name from ``jj log -r @- --no-graph -T bookmarks``.
    2. ``jj git push --allow-new``.

    Args:
        set_upstream: Ignored (jj manages tracking automatically).

    Returns:
        GitPushResult as dict.
    """
    try:
        # Get bookmark (branch) for the most recent commit
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            "@-",
            "--no-graph",
            "-T",
            "bookmarks",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj log failed: {stderr.decode()}")
        bookmark_raw = stdout.decode().strip()
        # bookmarks template may output "name@origin" or just "name"
        branch = bookmark_raw.split("@")[0] if bookmark_raw else ""
        if not branch:
            raise RuntimeError("No bookmark found on @- revision")

        # Push
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "git",
            "push",
            "--allow-new",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj git push failed: {stderr.decode()}")

        return {
            "success": True,
            "remote": "origin",
            "branch": branch,
            "upstream_set": True,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj push failed: {e}")
        return {
            "success": False,
            "remote": "origin",
            "branch": "",
            "upstream_set": False,
            "error": str(e),
        }


async def git_merge(branch: str, no_ff: bool = False) -> dict[str, Any]:
    """Merge a branch into the current change using jj.

    Creates a new merge change with two parents (current @ and the target
    bookmark), describes it, then starts a fresh change on top.

    Args:
        branch: Name of the bookmark (branch) to merge.
        no_ff: Ignored (jj always creates a merge node for multi-parent).

    Returns:
        Dict with:
        - success: True if merge succeeded
        - branch: The branch that was merged
        - merge_commit: SHA of the merge commit
        - error: Error message if failed, None otherwise
    """
    try:
        # Create merge change with two parents: current @ and target branch
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "new",
            "@",
            branch,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj new merge failed: {stderr.decode()}")

        # Check for conflicts
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "resolve",
            "--list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if stdout.decode().strip():
            raise RuntimeError(f"Merge has conflicts: {stdout.decode().strip()}")

        # Describe the merge
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "describe",
            "-m",
            f"merge: {branch}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj describe failed: {stderr.decode()}")

        # Start new change on top of merge
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "new",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj new failed: {stderr.decode()}")

        # Get the merge commit SHA (@- is now the merge change)
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "log",
            "-r",
            "@-",
            "--no-graph",
            "-T",
            'commit_id ++ "\n"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"jj log failed: {stderr.decode()}")
        merge_commit = stdout.decode().strip().split("\n")[0]

        logger.info("Merged branch via jj", branch=branch, merge_commit=merge_commit)

        return {
            "success": True,
            "branch": branch,
            "merge_commit": merge_commit,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj merge failed: {e}")
        return {
            "success": False,
            "branch": branch,
            "merge_commit": None,
            "error": str(e),
        }


async def create_git_branch(
    branch_name: str,
    base: str = "main",
) -> dict[str, Any]:
    """Create or switch to a bookmark (branch) in jj.

    Args:
        branch_name: Name of bookmark to create/switch to.
        base: Base revision to create from (default: main).

    Returns:
        GitBranchResult as dict.
    """
    try:
        # Check if bookmark exists
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "bookmark",
            "list",
            "--all-remotes",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        bookmark_output = stdout.decode()

        # Check if our bookmark name appears in the listing
        bookmark_exists = False
        for line in bookmark_output.splitlines():
            # jj bookmark list outputs lines like "name: revid description"
            if line.startswith(f"{branch_name}:") or line.startswith(f"{branch_name} "):
                bookmark_exists = True
                break

        if bookmark_exists:
            # Switch to existing bookmark
            proc = await asyncio.create_subprocess_exec(
                "jj",
                "edit",
                branch_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"jj edit failed: {stderr.decode()}")
            created = False
        else:
            # Create new change from base, then create bookmark
            proc = await asyncio.create_subprocess_exec(
                "jj",
                "new",
                base,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"jj new {base} failed: {stderr.decode()}")

            proc = await asyncio.create_subprocess_exec(
                "jj",
                "bookmark",
                "create",
                branch_name,
                "-r",
                "@",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"jj bookmark create failed: {stderr.decode()}")
            created = True

        return {
            "success": True,
            "branch_name": branch_name,
            "base_branch": base,
            "created": created,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"jj branch operation failed: {e}")
        return {
            "success": False,
            "branch_name": branch_name,
            "base_branch": base,
            "created": False,
            "error": str(e),
        }


# =============================================================================
# Tier 1b — Describe (set change description without committing)
# =============================================================================


async def jj_describe(message: str) -> dict[str, Any]:
    """Set the description of the current working-copy change.

    Unlike ``git_commit`` this does NOT call ``jj new`` afterwards,
    so the change stays editable.  Useful for labelling WIP changes
    at the start of a bead so ``jj log`` shows what is in-flight.

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
# Tier 2 — Operation log safety (new actions)
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
# Tier 3 — Post-hoc curation (new actions)
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


# =============================================================================
# Tier 4 — History curation (post-loop)
# =============================================================================

# Regex to detect "fix" beads — e.g. "bead(FIX-123): fix lint errors"
_FIX_BEAD_RE = "^bead\\(.*\\):"
_FIX_KEYWORD_RE = ("fix", "fixup", "lint", "format", "typecheck")


async def curate_history(
    base_revision: str = "main",
) -> dict[str, Any]:
    """Reorganize bead commits into cleaner history before push.

    Runs two passes:
    1. ``jj absorb`` — mechanically distributes stray hunks into the
       ancestor commits they logically belong to.
    2. Heuristic squash — any commit whose description contains fix/fixup
       keywords and shares modified files with its immediate parent gets
       squashed into that parent via ``jj squash``.

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
