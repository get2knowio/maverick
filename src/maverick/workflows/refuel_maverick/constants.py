"""Constants for RefuelMaverickWorkflow."""

from __future__ import annotations

# Step names
PARSE_FLIGHT_PLAN = "parse_flight_plan"
GATHER_CONTEXT = "gather_context"
BRIEFING = "briefing"
DERIVE_VERIFICATION = "derive_verification"
DECOMPOSE = "decompose"

#: Maximum work units per detail batch to stay within output token limits.
#: 10 balances token budget against the number of sequential agent calls
#: needed for large decompositions (e.g. 46 units = 5 batches, not 10).
DETAIL_BATCH_SIZE = 10

#: Maximum seeded detail turns to run on one ACP session before reseeding.
#: Detail turns are numerous, so a modest threshold amortizes the large seed
#: prompt without letting session history grow unbounded.
DETAIL_SESSION_MAX_TURNS = 5

#: Maximum seeded fix turns to run on one ACP session before reseeding.
#: Fix rounds mutate the decomposition state, so the first pass keeps the
#: threshold low and relies on refreshed context for each round.
FIX_SESSION_MAX_TURNS = 1

VALIDATE = "validate"
WRITE_WORK_UNITS = "write_work_units"
CREATE_BEADS = "create_beads"
WIRE_DEPS = "wire_deps"
ANALYZE_OPEN_BEADS = "analyze_open_beads"
WIRE_CROSS_PLAN_DEPS = "wire_cross_plan_deps"

# Default config values
WORKFLOW_NAME: str = "refuel-maverick"
