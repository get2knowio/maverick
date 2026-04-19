"""CommitActor — Thespian actor for jj commit and bead completion."""

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge

COMMIT_TIMEOUT_SECONDS = 300.0


class CommitActor(ActorAsyncBridge, Actor):
    """Deterministic commit via jj + bead status update."""

    def receiveMessage(self, message, sender):
        if self._handle_actor_exit(message):
            return
        if not isinstance(message, dict):
            return

        if message.get("type") == "commit":
            bead_id = message.get("bead_id", "")
            title = message.get("title", "")
            cwd = message.get("cwd")
            tag = message.get("tag")

            try:
                result = self._run_coro(
                    self._do_commit(bead_id, title, cwd, tag),
                    timeout=COMMIT_TIMEOUT_SECONDS,
                )
                self.send(sender, {"type": "commit_result", **result})
            except Exception as exc:
                self.send(
                    sender,
                    {
                        "type": "commit_result",
                        "success": False,
                        "error": str(exc),
                    },
                )

    async def _do_commit(self, bead_id, title, cwd, tag):
        from maverick.library.actions.beads import mark_bead_complete
        from maverick.library.actions.jj import jj_commit_bead

        commit_message = f"bead({bead_id}): {title}"
        if tag:
            commit_message = f"bead({bead_id}) [{tag}]: {title}"

        commit_result = await jj_commit_bead(message=commit_message, cwd=cwd)
        await mark_bead_complete(bead_id=bead_id)

        return {
            "success": commit_result.get("success", False),
            "commit_sha": commit_result.get("change_id"),
            "tag": tag,
        }
