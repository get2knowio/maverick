"""Constants for RefuelMaverickWorkflow."""

from __future__ import annotations

# Step names
PARSE_FLIGHT_PLAN = "parse_flight_plan"
GATHER_CONTEXT = "gather_context"
DECOMPOSE = "decompose"
VALIDATE = "validate"
WRITE_WORK_UNITS = "write_work_units"
CREATE_BEADS = "create_beads"
WIRE_DEPS = "wire_deps"

# Default config values
WORKFLOW_NAME: str = "refuel-maverick"
