"""Constants for GenerateFlightPlanWorkflow."""

from __future__ import annotations

# Step names
READ_PRD = "read_prd"
BRIEFING = "briefing"
BRIEFING_SCOPIST = "briefing_scopist"
BRIEFING_CODEBASE_ANALYST = "briefing_codebase_analyst"
BRIEFING_CRITERIA_WRITER = "briefing_criteria_writer"
BRIEFING_CONTRARIAN = "briefing_contrarian"
GENERATE = "generate"
VALIDATE = "validate"
WRITE_FLIGHT_PLAN = "write_flight_plan"

# Workflow name
WORKFLOW_NAME: str = "generate-flight-plan"
