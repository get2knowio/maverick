"""Constants for RefuelMaverickWorkflow."""

from __future__ import annotations

# Step names
PARSE_FLIGHT_PLAN = "parse_flight_plan"
GATHER_CONTEXT = "gather_context"
BRIEFING = "briefing"
BRIEFING_NAVIGATOR = "briefing_navigator"
BRIEFING_STRUCTURALIST = "briefing_structuralist"
BRIEFING_RECON = "briefing_recon"
BRIEFING_CONTRARIAN = "briefing_contrarian"
DECOMPOSE = "decompose"
VALIDATE = "validate"
WRITE_WORK_UNITS = "write_work_units"
CREATE_BEADS = "create_beads"
WIRE_DEPS = "wire_deps"

# Default config values
WORKFLOW_NAME: str = "refuel-maverick"
