"""xoscar PlanValidatorActor — deterministic flight-plan structure check.

Runs the V1-V9 validators from ``maverick.flight.validator`` against a
freshly-rendered flight-plan markdown. Returns warnings rather than
failing — a plan with warnings still proceeds to write.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import xoscar as xo

from maverick.actors.xoscar.messages import PlanValidateRequest, PlanValidateResult
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import SubmitFlightPlanPayload
from maverick.workflows.generate_flight_plan.markdown import (
    render_flight_plan_markdown,
)

logger = get_logger(__name__)


class PlanValidatorActor(xo.Actor):
    """Validates flight-plan structure by rendering + running validators."""

    async def validate(self, request: PlanValidateRequest) -> PlanValidateResult:
        try:
            from maverick.flight.validator import validate_flight_plan_file

            flight_plan = SubmitFlightPlanPayload.model_validate(request.flight_plan)
            plan_name = str(flight_plan.name or request.plan_name or "plan")
            markdown = render_flight_plan_markdown(
                plan_name=plan_name,
                prd_content=request.prd_content,
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
                warnings = tuple(
                    f"{issue.location}: {issue.message}" for issue in issues
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            return PlanValidateResult(passed=True, warnings=warnings)
        except Exception as exc:  # noqa: BLE001 — preserve legacy behaviour
            logger.warning("plan_validator.error", error=str(exc))
            return PlanValidateResult(passed=False, warnings=(str(exc),))
