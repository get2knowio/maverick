"""Constants for SpeckitRefuelWorkflow."""

from __future__ import annotations

# Step names
RESOLVE_FEATURE = "resolve_feature"
CHECK_TEMPLATE = "check_template"
PARSE_ARTIFACTS = "parse_artifacts"
PLAN_INGESTION = "plan_ingestion"
ENRICH = "enrich"
CREATE_BEADS = "create_beads"
WIRE_DEPS = "wire_deps"
CHAIN_EPIC = "chain_epic"
RECORD_RUN = "record_run"
COMMIT_OUTPUT = "commit_output"

WORKFLOW_NAME: str = "refuel-speckit"
