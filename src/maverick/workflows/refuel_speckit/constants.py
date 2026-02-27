"""Constants for RefuelSpeckitWorkflow."""

from __future__ import annotations

# Step names
CHECKOUT = "checkout"
CHECKOUT_MAIN = "checkout_main"
PARSE_SPEC = "parse_spec"
EXTRACT_DEPS = "extract_deps"
ENRICH_BEADS = "enrich_beads"
CREATE_BEADS = "create_beads"
WIRE_DEPS = "wire_deps"
COMMIT = "commit"
MERGE = "merge"

# Default config values
WORKFLOW_NAME: str = "refuel-speckit"
