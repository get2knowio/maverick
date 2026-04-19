"""PlanValidatorActor — Thespian actor for flight plan validation (V1-V9)."""

import tempfile
from pathlib import Path

from thespian.actors import Actor

from maverick.tools.supervisor_inbox.models import SubmitFlightPlanPayload
from maverick.workflows.generate_flight_plan.markdown import (
    render_flight_plan_markdown,
)


class PlanValidatorActor(Actor):
    """Deterministic validation of flight plan structure."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "validate":
            flight_plan_data = message.get("flight_plan", {})
            try:
                from maverick.flight.validator import validate_flight_plan_file

                flight_plan = SubmitFlightPlanPayload.model_validate(flight_plan_data)
                plan_name = str(flight_plan.name or message.get("plan_name") or "plan")
                prd_content = str(message.get("prd_content") or "")
                markdown = render_flight_plan_markdown(
                    plan_name=plan_name,
                    prd_content=prd_content,
                    flight_plan=flight_plan,
                )

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".md",
                    delete=False,
                    encoding="utf-8",
                ) as tmp:
                    tmp.write(markdown)
                    tmp_path = Path(tmp.name)

                try:
                    issues = validate_flight_plan_file(tmp_path)
                    warnings = [f"{issue.location}: {issue.message}" for issue in issues]
                finally:
                    tmp_path.unlink(missing_ok=True)
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
