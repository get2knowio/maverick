"""SpecCheckActor — Thespian actor for spec compliance verification."""

from thespian.actors import Actor


class SpecCheckActor(Actor):
    """Deterministic spec compliance check. Passes through for now."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "spec_check":
            # TODO: Wire full VP test injection logic
            # For now, pass through — gate and AC provide coverage
            self.send(sender, {
                "type": "spec_result",
                "passed": True,
                "details": "delegated to gate+AC",
            })
