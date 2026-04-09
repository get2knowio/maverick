"""PlanValidatorActor — Thespian actor for flight plan validation (V1-V9)."""

from thespian.actors import Actor


class PlanValidatorActor(Actor):
    """Deterministic validation of flight plan structure."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "validate":
            flight_plan_data = message.get("flight_plan", {})
            try:
                from maverick.flight.validator import validate_flight_plan

                warnings = validate_flight_plan(flight_plan_data)
                self.send(
                    sender,
                    {
                        "type": "validation_result",
                        "passed": True,
                        "warnings": warnings or [],
                    },
                )
            except Exception as exc:
                self.send(
                    sender,
                    {
                        "type": "validation_result",
                        "passed": False,
                        "warnings": [str(exc)],
                    },
                )
