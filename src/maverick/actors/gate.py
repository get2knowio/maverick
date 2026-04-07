"""GateActor — Thespian actor for validation gate (build/lint/test)."""

import asyncio

from thespian.actors import Actor


class GateActor(Actor):
    """Deterministic validation gate. Runs cargo build/clippy/test."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "init":
            self._cwd = message.get("cwd")
            self._validation_commands = message.get("validation_commands")
            self._timeout = message.get("timeout_seconds", 600.0)
            self.send(sender, {"type": "init_ok"})

        elif message.get("type") == "gate":
            try:
                result = asyncio.run(self._run_gate())
                self.send(sender, {"type": "gate_result", **result})
            except Exception as exc:
                self.send(sender, {
                    "type": "gate_result",
                    "passed": False,
                    "summary": f"Gate error: {exc}",
                })

    async def _run_gate(self):
        from maverick.library.actions.validation import (
            run_independent_gate,
        )
        from maverick.workflows.fly_beads.constants import (
            DEFAULT_VALIDATION_STAGES,
        )

        return await run_independent_gate(
            stages=list(DEFAULT_VALIDATION_STAGES),
            cwd=self._cwd,
            validation_commands=self._validation_commands,
            timeout_seconds=self._timeout,
        )
