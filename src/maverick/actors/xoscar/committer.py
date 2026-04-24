"""xoscar CommitterActor — jj commit + bead completion."""

from __future__ import annotations

import xoscar as xo

from maverick.actors.xoscar.messages import CommitRequest, CommitResult
from maverick.logging import get_logger

logger = get_logger(__name__)

COMMIT_TIMEOUT_SECONDS = 300.0


class CommitterActor(xo.Actor):
    """Deterministic commit via jj + bead status update."""

    async def commit(self, request: CommitRequest) -> CommitResult:
        from maverick.library.actions.beads import mark_bead_complete
        from maverick.library.actions.jj import jj_commit_bead

        commit_message = f"bead({request.bead_id}): {request.title}"
        if request.tag:
            commit_message = f"bead({request.bead_id}) [{request.tag}]: {request.title}"

        try:
            commit = await jj_commit_bead(message=commit_message, cwd=request.cwd)
            await mark_bead_complete(bead_id=request.bead_id)
            return CommitResult(
                success=bool(commit.get("success", False)),
                commit_sha=commit.get("change_id"),
                tag=request.tag,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("committer.error", error=str(exc))
            return CommitResult(success=False, tag=request.tag, error=str(exc))
