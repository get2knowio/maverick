"""xoscar CommitterActor — jj commit + bead completion."""

from __future__ import annotations

import xoscar as xo

from maverick.actors.xoscar.messages import CommitRequest, CommitResult
from maverick.logging import get_logger

logger = get_logger(__name__)

COMMIT_TIMEOUT_SECONDS = 300.0


def _build_commit_message(bead_id: str, title: str, tag: str | None) -> str:
    """Build the bead commit message with optional ``[tag]`` and the
    standard ``Bead:`` git trailer.

    Mirrors ``workflows.fly_beads._commit.build_bead_commit_message``
    but supports the per-bead ``tag`` (``[needs-human-review]`` etc.)
    that the actor surface carries.
    """
    subject = f"bead({bead_id}): {title}"
    if tag:
        subject = f"bead({bead_id}) [{tag}]: {title}"
    return f"{subject}\n\nBead: {bead_id}"


class CommitterActor(xo.Actor):
    """Deterministic per-bead commit + bead-state update.

    Calls :func:`jj_commit_bead` against the workspace cwd. The
    workspace is always a jj repo (created via
    ``WorkspaceManager.find_or_create()`` which colocates the user
    repo first), so we don't need vcs detection here.
    """

    async def commit(self, request: CommitRequest) -> CommitResult:
        from maverick.library.actions.beads import mark_bead_complete
        from maverick.library.actions.jj import jj_commit_bead

        commit_message = _build_commit_message(request.bead_id, request.title, request.tag)

        try:
            commit = await jj_commit_bead(message=commit_message, cwd=request.cwd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("committer.commit_call_error", error=str(exc))
            return CommitResult(success=False, tag=request.tag, error=str(exc))

        commit_ok = bool(commit.get("success", False))
        if not commit_ok:
            # Don't close the bead when the commit didn't land. Earlier
            # revisions called ``mark_bead_complete`` unconditionally,
            # which silently closed beads whose work never got
            # persisted — the next fly couldn't re-process them, and
            # the only signal of trouble was the supervisor's "Commit
            # failed for X:" log line.
            return CommitResult(
                success=False,
                commit_sha=commit.get("change_id"),
                tag=request.tag,
                error=str(commit.get("error") or ""),
            )

        try:
            await mark_bead_complete(bead_id=request.bead_id, cwd=request.cwd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("committer.mark_complete_error", error=str(exc))
            return CommitResult(
                success=False,
                commit_sha=commit.get("change_id"),
                tag=request.tag,
                error=f"mark_bead_complete failed: {exc}",
            )

        return CommitResult(
            success=True,
            commit_sha=commit.get("change_id"),
            tag=request.tag,
            error="",
        )
