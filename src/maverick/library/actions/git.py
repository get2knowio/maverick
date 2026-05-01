"""Git actions for workflow execution.

All functions accept an optional ``cwd`` parameter.  When omitted, the
current working directory is used (backward compatible).  When provided,
subprocess calls target that directory.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from maverick.library.actions.git_models import (
    GitMergeResult,
    GitStatusResult,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

_UNTRACKED_CONFLICT_RE = re.compile(r"^\t(.+)$", re.MULTILINE)

# Files matching this prefix are managed by bd's dolt backend, which
# regenerates them on demand from the shared dolt database. Modify/delete
# merge conflicts on these paths are spurious — both branches share the
# same dolt state, only the JSONL projection diverged. ``git_merge``
# resolves them by accepting deletion (bd will regenerate). FUTURE.md §4.4.
_DOLT_MANAGED_PREFIX = ".beads/"

# git status --porcelain=v1 codes for unmerged entries.
_UNMERGED_STATUS_CODES = frozenset({"DU", "UD", "AA", "DD", "AU", "UA", "UU"})


def _resolve_cwd(cwd: str | Path | None) -> str | None:
    """Convert *cwd* to a string path for subprocess, or None for default."""
    if cwd is None:
        return None
    return str(Path(cwd))


def _reap_if_running(proc: asyncio.subprocess.Process | None) -> None:
    """Kill the process group of a subprocess that never finished.

    Subprocesses spawned with ``start_new_session=True`` live in their own
    process group. If the helper was cancelled mid-flight (Ctrl-C, task
    cancellation), parent death will not propagate to the child; we must
    actively reap. If the process already exited, this is a no-op.
    """
    if proc is None or proc.returncode is not None:
        return
    from maverick.executor._subprocess import kill_process_group

    kill_process_group(proc.pid)


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


async def _git_unmerged_paths(cwd: str | None) -> list[tuple[str, str]]:
    """Return ``(status_code, path)`` for every unmerged path.

    Used to triage merge conflicts after ``git merge`` has left the
    working tree in a partially-merged state. Status codes follow
    ``git status --porcelain=v1``: e.g. ``UD`` is "modified by us,
    deleted by them".
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "status",
        "--porcelain=v1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        stdout, _ = await proc.communicate()
    finally:
        _reap_if_running(proc)
    result: list[tuple[str, str]] = []
    for line in stdout.decode(errors="replace").splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:]
        if code in _UNMERGED_STATUS_CODES:
            result.append((code, path))
    return result


async def _abort_merge(cwd: str | None) -> None:
    """Run ``git merge --abort`` to restore a clean working tree.

    Best-effort: if the abort itself fails, log and continue so the
    caller can still surface the original failure.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "merge",
        "--abort",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        await proc.communicate()
    finally:
        _reap_if_running(proc)


async def git_has_changes(
    cwd: str | Path | None = None,
) -> GitStatusResult:
    """Check if there are staged or unstaged changes to commit.

    Args:
        cwd: Working directory. Defaults to process cwd.

    Returns:
        :class:`GitStatusResult` with staged/unstaged/untracked/any flags.
    """
    resolved = _resolve_cwd(cwd)

    async def _name_only(*args: str) -> tuple[str, ...]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=resolved,
            start_new_session=True,
        )
        out, _ = await proc.communicate()
        return tuple(line for line in out.decode().splitlines() if line.strip())

    try:
        # Capture filenames in one pass per category — we need them for
        # error messages anyway, so the older two-step "quiet" probes
        # are redundant. Empty tuple == no changes.
        staged_files = await _name_only("diff", "--cached", "--name-only")
        unstaged_files = await _name_only("diff", "--name-only")
        untracked_files = await _name_only(
            "ls-files",
            "--others",
            "--exclude-standard",
        )

        has_staged = bool(staged_files)
        has_unstaged = bool(unstaged_files)
        has_untracked = bool(untracked_files)
        has_any = has_staged or has_unstaged or has_untracked

        logger.debug(
            "Git change status",
            has_staged=has_staged,
            has_unstaged=has_unstaged,
            has_untracked=has_untracked,
            has_any=has_any,
        )

        return GitStatusResult(
            has_staged=has_staged,
            has_unstaged=has_unstaged,
            has_untracked=has_untracked,
            has_any=has_any,
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            untracked_files=untracked_files,
        )

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git status check failed: {e}")
        # On error, assume there might be changes to be safe
        return GitStatusResult(
            has_staged=True,
            has_unstaged=True,
            has_untracked=True,
            has_any=True,
        )


async def git_merge(
    branch: str,
    no_ff: bool = False,
    cwd: str | Path | None = None,
) -> GitMergeResult:
    """Merge a branch into the current branch.

    Args:
        branch: Name of the branch to merge into the current branch.
        no_ff: If True, create a merge commit even for fast-forward merges.
        cwd: Working directory. Defaults to process cwd.

    Returns:
        :class:`GitMergeResult`.
    """
    resolved = _resolve_cwd(cwd)
    proc: asyncio.subprocess.Process | None = None
    rm_proc: asyncio.subprocess.Process | None = None
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
            start_new_session=True,
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
                        start_new_session=True,
                    )
                    await rm_proc.wait()
                    rm_proc = None

                # Retry the merge
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=resolved,
                    start_new_session=True,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    retry_combined = (stdout + stderr).decode(errors="replace")
                    raise RuntimeError(
                        f"git merge failed after removing untracked conflicts: {retry_combined}"
                    )
            elif "CONFLICT (modify/delete)" in combined:
                # ``.beads/`` is a dolt-managed working area: bd
                # regenerates files (notably ``issues.jsonl``) on demand
                # from the shared dolt DB. When the workspace branch has
                # the JSONL view deleted while the user's HEAD has it
                # modified (or vice versa), git can't tell that both
                # sides actually share the same dolt state — it stops
                # the merge with a "modify/delete" conflict that's
                # spurious. (FUTURE.md §4.4)
                #
                # If ALL unmerged paths are dolt-managed modify/delete
                # conflicts, resolve by accepting deletion (bd will
                # regenerate). Real conflicts on other paths still fail
                # loudly so the caller can address them.
                unmerged = await _git_unmerged_paths(resolved)
                dolt_paths: list[str] = []
                non_dolt_unmerged: list[str] = []
                for code, path in unmerged:
                    if code in ("UD", "DU") and path.startswith(_DOLT_MANAGED_PREFIX):
                        dolt_paths.append(path)
                    else:
                        non_dolt_unmerged.append(f"{code} {path}")

                if non_dolt_unmerged or not dolt_paths:
                    # Either there are real conflicts we can't resolve,
                    # or this isn't actually a dolt-only modify/delete
                    # case. Abort to restore a clean working tree, then
                    # bubble the original failure.
                    await _abort_merge(resolved)
                    raise RuntimeError(f"git merge failed: {combined}")

                for path in dolt_paths:
                    logger.info(
                        "Resolving dolt-managed modify/delete by accepting deletion",
                        path=path,
                    )
                    rm_proc = await asyncio.create_subprocess_exec(
                        "git",
                        "rm",
                        "-f",
                        path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=resolved,
                        start_new_session=True,
                    )
                    await rm_proc.wait()
                    rm_proc = None

                # Complete the merge with the auto-generated MERGE_MSG
                # that git already prepared. ``--no-edit`` skips the
                # commit-message editor.
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "commit",
                    "--no-edit",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=resolved,
                    start_new_session=True,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    retry_combined = (stdout + stderr).decode(errors="replace")
                    raise RuntimeError(
                        "git merge failed to complete after resolving dolt-managed "
                        f"conflicts: {retry_combined}"
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
            start_new_session=True,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {stderr.decode()}")
        merge_commit = stdout.decode().strip()

        logger.info("Merged branch", branch=branch, merge_commit=merge_commit)

        return GitMergeResult(
            success=True,
            branch=branch,
            merge_commit=merge_commit,
        )

    except (RuntimeError, OSError) as e:
        logger.debug(f"Git merge failed: {e}")
        return GitMergeResult(
            success=False,
            branch=branch,
            error=str(e),
        )
    finally:
        _reap_if_running(proc)
        _reap_if_running(rm_proc)
