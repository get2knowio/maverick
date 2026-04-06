"""ValidatorActor — Thespian actor for decomposition validation.

Pure synchronous — no async bridge needed. Receives specs,
validates SC coverage and dependency acyclicity, returns result.
"""

from thespian.actors import Actor


class ValidatorActor(Actor):
    """Validates decomposition specs against flight plan criteria."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            # Store flight plan for validation
            self._flight_plan = message.get("flight_plan")
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "validate":
            specs = message.get("specs", [])
            try:
                from maverick.library.actions.decompose import (
                    SCCoverageError,
                    validate_decomposition,
                )

                validate_decomposition(
                    specs=specs,
                    flight_plan=getattr(self, "_flight_plan", None),
                )
                self.send(sender, {"type": "validation_result", "passed": True})

            except SCCoverageError as exc:
                self.send(sender, {
                    "type": "validation_result",
                    "passed": False,
                    "error_type": "coverage",
                    "gaps": list(exc.gaps) if exc.gaps else [],
                    "message": str(exc),
                })

            except Exception as exc:
                self.send(sender, {
                    "type": "validation_result",
                    "passed": False,
                    "error_type": "other",
                    "gaps": [],
                    "message": str(exc),
                })
