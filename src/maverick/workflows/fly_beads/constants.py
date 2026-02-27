"""Constants for FlyBeadsWorkflow."""

from __future__ import annotations

# Step names
PREFLIGHT = "preflight"
CREATE_WORKSPACE = "create_workspace"
SELECT_BEAD = "select_bead"
IMPLEMENT = "implement"
SYNC_DEPS = "sync_deps"
VALIDATE = "validate"
REVIEW = "review"
COMMIT = "commit"

# Default config values
MAX_BEADS: int = 30
WORKFLOW_NAME: str = "fly-beads"
