"""Git actions for workflow execution.

All functions accept an optional ``cwd`` parameter.  When omitted, the
current working directory is used (backward compatible).  When provided,
subprocess calls target that directory.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

_UNTRACKED_CONFLICT_RE = re.compile(r"^\t(.+)$", re.MULTILINE)


def _resolve_cwd(cwd: str | Path | None) -> str | None:
    """Convert *cwd* to a string path for subprocess, or None for default."""
    if cwd is None:
        return None
    return str(Path(cwd))


def _parse_untracked_conflicts(git_output: str) -> list[str]:
    """Extract file paths from a git 'untracked working tree files' error.

    Git outputs conflicting paths indented with a tab character between
    the header and the 'Please move or remove' footer.
    """
    # Only look at lines between the header and footer markers
    start = git_output.find("would be overwritten by merge:")
    end = git_output.find("Please move or remove")
    if start == -1 or end == -1:
        return []
    section = git_output[start:end]
    return [m.group(1).strip() for m in _UNTRACKED_CONFLICT_RE.finditer(section)]


async def git_has_changes(
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Check if there are staged or unstaged changes to commit.

    Args:
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - has_staged: True if there are staged changes
        - has_unstaged: True if there are unstaged changes
        - has_untracked: True if there are untracked files
        - has_any: True if any changes exist (staged, unstaged, or untracked)
    """
    resolved = _resolve_cwd(cwd)
    try:
        # Check for staged changes
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--cached",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        await proc.wait()
        has_staged = proc.returncode != 0

        # Check for unstaged changes
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        await proc.wait()
        has_unstaged = proc.returncode != 0

        # Check for untracked files
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, _ = await proc.communicate()
        has_untracked = bool(stdout.decode().strip())

        has_any = has_staged or has_unstaged or has_untracked

        logger.debug(
            "Git change status",
            has_staged=has_staged,
            has_unstaged=has_unstaged,
            has_untracked=has_untracked,
            has_any=has_any,
        )

        return {
            "has_staged": has_staged,
            "has_unstaged": has_unstaged,
            "has_untracked": has_untracked,
            "has_any": has_any,
        }

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git status check failed: {e}")
        # On error, assume there might be changes to be safe
        return {
            "has_staged": True,
            "has_unstaged": True,
            "has_untracked": True,
            "has_any": True,
        }


async def git_check_and_stage(
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Check for changes and stage them if any exist.

    Combines the check and stage operations into a single action so that
    ``git diff --cached`` returns a meaningful diff for the commit message
    generator.  If no changes are detected the staging step is skipped.

    Args:
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - has_staged: True if there are staged changes
        - has_unstaged: True if there are unstaged changes
        - has_untracked: True if there are untracked files
        - has_any: True if any changes exist (staged, unstaged, or untracked)
    """
    # Reuse git_has_changes for the detection logic
    status = await git_has_changes(cwd=cwd)

    if status["has_any"]:
        stage_result = await git_stage_all(cwd=cwd)
        if not stage_result["success"]:
            logger.debug("Failed to stage changes: %s", stage_result.get("error"))
            # Still return the status so callers know changes exist even
            # though staging failed – downstream steps will see has_any=True
            # and attempt their own staging via git_commit(add_all=True).

    return status


async def git_add(
    paths: list[str] | None = None,
    force: bool = False,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Stage specific paths (with optional force for excluded files).

    Args:
        paths: File paths to stage. Defaults to ["."] if not provided.
        force: Use ``git add -f`` to override .gitignore / info/exclude.
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - success: True if staging succeeded
        - error: Error message if staging failed, None otherwise
    """
    if not paths:
        paths = ["."]

    resolved = _resolve_cwd(cwd)
    try:
        cmd = ["git", "add"]
        if force:
            cmd.append("-f")
        cmd.extend(paths)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git add failed: {stderr.decode()}")

        logger.debug("Staged paths", paths=paths, force=force)
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git add failed: {e}")
        return {"success": False, "error": str(e)}


async def git_stage_all(
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Stage all changes including untracked files (git add .).

    This is useful before generating commit messages, so that `git diff --cached`
    captures newly-created files that would otherwise be invisible to diff.

    Args:
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - success: True if staging succeeded
        - error: Error message if staging failed, None otherwise
    """
    resolved = _resolve_cwd(cwd)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "add",
            ".",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        await proc.wait()
        if proc.returncode != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            raise RuntimeError(f"git add failed: {stderr.decode()}")

        logger.debug("Staged all changes")
        return {"success": True, "error": None}

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git stage all failed: {e}")
        return {"success": False, "error": str(e)}


async def git_commit(
    message: str,
    add_all: bool = True,
    include_attribution: bool = True,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Create a git commit with the given message.

    Args:
        message: Commit message
        add_all: Whether to stage all changes (git add .)
        include_attribution: Include AI co-author attribution
        cwd: Working directory. Defaults to process cwd.

    Returns:
        GitCommitResult as dict
    """
    resolved = _resolve_cwd(cwd)
    try:
        if add_all:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "add",
                ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved,
            )
            await proc.wait()
            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                raise RuntimeError(f"git add failed: {stderr.decode()}")

        # Build commit message with attribution
        full_message = message
        if include_attribution:
            attribution = (
                "\n\n🤖 Generated with Claude Code\n\n"
                "Co-Authored-By: Claude <noreply@anthropic.com>"
            )
            full_message += attribution

        # Create commit
        proc = await asyncio.create_subprocess_exec(
            "git",
            "commit",
            "-m",
            full_message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            combined = (stdout_bytes + stderr_bytes).decode(errors="replace")
            if "nothing to commit" in combined:
                return {
                    "success": True,
                    "commit_sha": None,
                    "files_committed": [],
                    "message": message,
                    "nothing_to_commit": True,
                }
            raise RuntimeError(f"git commit failed: {combined}")

        # Get commit SHA
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {stderr.decode()}")
        commit_sha = stdout.decode().strip()

        # Get list of committed files
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, _ = await proc.communicate()
        files_committed = (
            tuple(stdout.decode().strip().split("\n")) if stdout.decode().strip() else ()
        )

        return {
            "success": True,
            "commit_sha": commit_sha,
            "message": message,
            "files_committed": files_committed,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git commit failed: {e}")
        return {
            "success": False,
            "commit_sha": None,
            "message": message,
            "files_committed": (),
            "error": str(e),
        }


async def git_push(
    set_upstream: bool = True,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Push current branch to remote.

    Args:
        set_upstream: Whether to set upstream tracking
        cwd: Working directory. Defaults to process cwd.

    Returns:
        GitPushResult as dict
    """
    resolved = _resolve_cwd(cwd)
    try:
        # Get current branch
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {stderr.decode()}")
        branch = stdout.decode().strip()

        # Push with or without upstream
        cmd = ["git", "push"]
        if set_upstream:
            cmd.extend(["-u", "origin", branch])
        else:
            cmd.extend(["origin", branch])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        await proc.wait()
        if proc.returncode != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            raise RuntimeError(f"git push failed: {stderr.decode()}")

        return {
            "success": True,
            "remote": "origin",
            "branch": branch,
            "upstream_set": set_upstream,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git push failed: {e}")
        return {
            "success": False,
            "remote": "origin",
            "branch": "",
            "upstream_set": False,
            "error": str(e),
        }


async def git_merge(
    branch: str,
    no_ff: bool = False,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Merge a branch into the current branch.

    Args:
        branch: Name of the branch to merge into the current branch.
        no_ff: If True, create a merge commit even for fast-forward merges.
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - success: True if merge succeeded
        - branch: The branch that was merged
        - merge_commit: SHA of the merge commit (or HEAD after fast-forward)
        - error: Error message if merge failed, None otherwise
    """
    resolved = _resolve_cwd(cwd)
    try:
        cmd = ["git", "merge"]
        if no_ff:
            cmd.append("--no-ff")
        cmd.append(branch)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            combined = (stdout + stderr).decode(errors="replace")
            if "already up to date" in combined.lower():
                # Not an error — target branch already contains the source
                pass
            elif "untracked working tree files would be overwritten" in combined:
                # A background process (e.g. bd daemon) recreated files that
                # git removed during checkout.  Remove the conflicting
                # untracked files and retry — the merge will bring the correct
                # versions from the source branch.
                untracked = _parse_untracked_conflicts(combined)
                for path in untracked:
                    logger.info("Removing untracked conflict", path=path)
                    rm_proc = await asyncio.create_subprocess_exec(
                        "rm",
                        "-f",
                        path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=resolved,
                    )
                    await rm_proc.wait()

                # Retry the merge
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=resolved,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    retry_combined = (stdout + stderr).decode(errors="replace")
                    raise RuntimeError(
                        f"git merge failed after removing untracked conflicts: {retry_combined}"
                    )
            else:
                raise RuntimeError(f"git merge failed: {combined}")

        # Get the resulting HEAD commit SHA
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {stderr.decode()}")
        merge_commit = stdout.decode().strip()

        logger.info("Merged branch", branch=branch, merge_commit=merge_commit)

        return {
            "success": True,
            "branch": branch,
            "merge_commit": merge_commit,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git merge failed: {e}")
        return {
            "success": False,
            "branch": branch,
            "merge_commit": None,
            "error": str(e),
        }


# Snapshot commits exceeding this many changed files get a warning
# appended to their commit message so the curator can flag them.
_SNAPSHOT_FILE_THRESHOLD = 10


async def _get_snapshot_diff_stats(
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Get diff stats for uncommitted changes (files, insertions, deletions).

    Returns dict with file_count, insertions, deletions, files list.
    """
    resolved = _resolve_cwd(cwd)
    stats: dict[str, Any] = {
        "file_count": 0,
        "insertions": 0,
        "deletions": 0,
        "files": [],
    }

    try:
        # Get file list (staged + unstaged + untracked)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--stat",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout, _ = await proc.communicate()
        if stdout:
            lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
            # Last line is summary: " N files changed, M insertions(+), K deletions(-)"
            if lines:
                summary = lines[-1]
                import re

                m = re.search(r"(\d+) files? changed", summary)
                if m:
                    stats["file_count"] = int(m.group(1))
                m = re.search(r"(\d+) insertions?", summary)
                if m:
                    stats["insertions"] = int(m.group(1))
                m = re.search(r"(\d+) deletions?", summary)
                if m:
                    stats["deletions"] = int(m.group(1))

        # Get file names
        proc2 = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--name-only",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        stdout2, _ = await proc2.communicate()
        if stdout2:
            stats["files"] = [
                f.strip() for f in stdout2.decode().strip().splitlines() if f.strip()
            ]
            # Update count from name-only if stat didn't produce one
            if not stats["file_count"]:
                stats["file_count"] = len(stats["files"])
    except Exception:
        pass

    return stats


async def snapshot_uncommitted_changes(
    message: str = "chore: snapshot uncommitted changes before fly",
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Stage and commit all uncommitted changes (staged, unstaged, untracked).

    Used by ``maverick fly`` to ensure ``jj git clone`` picks up all local
    state (e.g. files created by ``maverick init``).

    When the snapshot exceeds ``_SNAPSHOT_FILE_THRESHOLD`` files, a warning
    with diff stats is appended to the commit message so the curator can
    flag large snapshots during curation.

    Args:
        message: Commit message for the snapshot.
        cwd: Working directory. Defaults to process cwd.

    Returns:
        Dict with:
        - success: True if a commit was created or there was nothing to commit
        - committed: True if a new commit was created
        - commit_sha: SHA of the new commit (if created)
        - diff_stats: Dict with file_count, insertions, deletions
        - warning: Human-readable warning if snapshot is large
        - error: Error message on failure
    """
    status = await git_has_changes(cwd=cwd)
    if not status["has_any"]:
        return {
            "success": True,
            "committed": False,
            "commit_sha": None,
            "diff_stats": None,
            "warning": None,
            "error": None,
        }

    # Check diff size before committing
    diff_stats = await _get_snapshot_diff_stats(cwd=cwd)
    warning = None

    # Annotate commit message if the snapshot is large
    effective_message = message
    if diff_stats["file_count"] > _SNAPSHOT_FILE_THRESHOLD:
        warning = (
            f"Large snapshot: {diff_stats['file_count']} files, "
            f"+{diff_stats['insertions']}/-{diff_stats['deletions']} lines. "
            "Review before merging — may contain unrelated changes."
        )
        effective_message = (
            f"{message}\n\n"
            f"WARNING: {warning}\n\n"
            f"Files ({diff_stats['file_count']}):\n"
            + "\n".join(f"  {f}" for f in diff_stats.get("files", [])[:30])
        )

    result = await git_commit(
        message=effective_message,
        add_all=True,
        include_attribution=False,
        cwd=cwd,
    )
    if not result["success"]:
        return {
            "success": False,
            "committed": False,
            "commit_sha": None,
            "diff_stats": diff_stats,
            "warning": warning,
            "error": result.get("error", "commit failed"),
        }

    return {
        "success": True,
        "committed": True,
        "commit_sha": result.get("commit_sha"),
        "diff_stats": diff_stats,
        "warning": warning,
        "error": None,
    }


async def create_git_branch(
    branch_name: str,
    base: str = "main",
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Create or checkout a git branch.

    Args:
        branch_name: Name of branch to create/checkout
        base: Base branch to create from (default: main)
        cwd: Working directory. Defaults to process cwd.

    Returns:
        GitBranchResult as dict
    """
    resolved = _resolve_cwd(cwd)
    try:
        # Check if branch exists
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--verify",
            branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
        )
        await proc.wait()
        branch_exists = proc.returncode == 0

        if branch_exists:
            # Checkout existing branch
            proc = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                branch_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved,
            )
            await proc.wait()
            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                raise RuntimeError(f"git checkout failed: {stderr.decode()}")
            created = False
        else:
            # Create new branch from base
            proc = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                base,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved,
            )
            await proc.wait()
            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                raise RuntimeError(f"git checkout base failed: {stderr.decode()}")

            proc = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                "-b",
                branch_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved,
            )
            await proc.wait()
            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                raise RuntimeError(f"git checkout -b failed: {stderr.decode()}")
            created = True

        return {
            "success": True,
            "branch_name": branch_name,
            "base_branch": base,
            "created": created,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.debug(f"Branch operation failed: {e}")
        return {
            "success": False,
            "branch_name": branch_name,
            "base_branch": base,
            "created": False,
            "error": str(e),
        }
