"""Git actions for workflow execution."""

from __future__ import annotations

import asyncio
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


async def git_has_changes() -> dict[str, Any]:
    """Check if there are staged or unstaged changes to commit.

    Returns:
        Dict with:
        - has_staged: True if there are staged changes
        - has_unstaged: True if there are unstaged changes
        - has_untracked: True if there are untracked files
        - has_any: True if any changes exist (staged, unstaged, or untracked)
    """
    try:
        # Check for staged changes
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--cached",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        logger.error(f"Git status check failed: {e}")
        # On error, assume there might be changes to be safe
        return {
            "has_staged": True,
            "has_unstaged": True,
            "has_untracked": True,
            "has_any": True,
        }


async def git_commit(
    message: str,
    add_all: bool = True,
    include_attribution: bool = True,
) -> dict[str, Any]:
    """Create a git commit with the given message.

    Args:
        message: Commit message
        add_all: Whether to stage all changes (git add .)
        include_attribution: Include AI co-author attribution

    Returns:
        GitCommitResult as dict
    """
    try:
        if add_all:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "add",
                ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        )
        await proc.wait()
        if proc.returncode != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            raise RuntimeError(f"git commit failed: {stderr.decode()}")

        # Get commit SHA
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        )
        stdout, _ = await proc.communicate()
        files_committed = (
            tuple(stdout.decode().strip().split("\n"))
            if stdout.decode().strip()
            else ()
        )

        return {
            "success": True,
            "commit_sha": commit_sha,
            "message": message,
            "files_committed": files_committed,
            "error": None,
        }

    except (RuntimeError, OSError) as e:
        logger.error(f"Git commit failed: {e}")
        return {
            "success": False,
            "commit_sha": None,
            "message": message,
            "files_committed": (),
            "error": str(e),
        }


async def git_push(set_upstream: bool = True) -> dict[str, Any]:
    """Push current branch to remote.

    Args:
        set_upstream: Whether to set upstream tracking

    Returns:
        GitPushResult as dict
    """
    try:
        # Get current branch
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        logger.error(f"Git push failed: {e}")
        return {
            "success": False,
            "remote": "origin",
            "branch": "",
            "upstream_set": False,
            "error": str(e),
        }


async def create_git_branch(
    branch_name: str,
    base: str = "main",
) -> dict[str, Any]:
    """Create or checkout a git branch.

    Args:
        branch_name: Name of branch to create/checkout
        base: Base branch to create from (default: main)

    Returns:
        GitBranchResult as dict
    """
    try:
        # Check if branch exists
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--verify",
            branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        logger.error(f"Branch operation failed: {e}")
        return {
            "success": False,
            "branch_name": branch_name,
            "base_branch": base,
            "created": False,
            "error": str(e),
        }
