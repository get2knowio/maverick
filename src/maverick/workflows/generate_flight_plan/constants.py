"""Constants for GenerateFlightPlanWorkflow."""

from __future__ import annotations

# Step names
READ_PRD = "read_prd"
BRIEFING = "briefing"
BRIEFING_SCOPIST = "briefing:scopist"
BRIEFING_CODEBASE_ANALYST = "briefing:codebase_analyst"
BRIEFING_CRITERIA_WRITER = "briefing:criteria_writer"
BRIEFING_CONTRARIAN = "briefing:contrarian"
GENERATE = "generate"
VALIDATE = "validate"
WRITE_FLIGHT_PLAN = "write_flight_plan"

# Workflow name
WORKFLOW_NAME: str = "generate-flight-plan"
