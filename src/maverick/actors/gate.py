"""GateActor — Thespian actor for validation gate (build/lint/test)."""

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge

DEFAULT_GATE_TIMEOUT_SECONDS = 600.0


class GateActor(ActorAsyncBridge, Actor):
    """Deterministic validation gate. Runs cargo build/clippy/test."""

    def receiveMessage(self, message, sender):
        if self._handle_actor_exit(message):
            return
        if not isinstance(message, dict):
            return

        if message.get("type") == "init":
            self._cwd = message.get("cwd")
            self._validation_commands = message.get("validation_commands")
            self._timeout = message.get("timeout_seconds", DEFAULT_GATE_TIMEOUT_SECONDS)
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif message.get("type") == "gate":
            try:
                result = self._run_coro(
                    self._run_gate(),
                    timeout=float(getattr(self, "_timeout", DEFAULT_GATE_TIMEOUT_SECONDS)),
                )
                self.send(sender, {"type": "gate_result", **result})
            except Exception as exc:
                self.send(
                    sender,
                    {
                        "type": "gate_result",
                        "passed": False,
                        "summary": f"Gate error: {exc}",
                    },
                )

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
