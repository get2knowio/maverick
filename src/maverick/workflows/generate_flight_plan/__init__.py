"""GenerateFlightPlanWorkflow package."""

from __future__ import annotations

from maverick.workflows.generate_flight_plan.models import GenerateFlightPlanResult
from maverick.workflows.generate_flight_plan.workflow import GenerateFlightPlanWorkflow

__all__ = ["GenerateFlightPlanWorkflow", "GenerateFlightPlanResult"]
