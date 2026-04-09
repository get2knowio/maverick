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
            self._flight_plan = message.get("flight_plan")
            # Extract SC count and refs from flight plan
            sc_list = getattr(self._flight_plan, "success_criteria", [])
            self._sc_count = len(sc_list)
            self._sc_refs = []
            for i, sc in enumerate(sc_list):
                ref = getattr(sc, "ref", None) or f"SC-{i + 1:03d}"
                self._sc_refs.append(ref)
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
                    success_criteria_count=getattr(self, "_sc_count", 0),
                    expected_sc_refs=getattr(self, "_sc_refs", None),
                )
                self.send(sender, {"type": "validation_result", "passed": True})

            except SCCoverageError as exc:
                self.send(
                    sender,
                    {
                        "type": "validation_result",
                        "passed": False,
                        "error_type": "coverage",
                        "gaps": list(exc.gaps) if exc.gaps else [],
                        "message": str(exc),
                    },
                )

            except Exception as exc:
                import sys

                print(f"VALIDATOR: error: {exc}", file=sys.stderr, flush=True)
                self.send(
                    sender,
                    {
                        "type": "validation_result",
                        "passed": False,
                        "error_type": "other",
                        "gaps": [],
                        "message": str(exc),
                    },
                )
