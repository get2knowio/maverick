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

# Bead execution defaults
MAX_VERIFY_CYCLES: int = 2
DEFAULT_MAX_FIX_ATTEMPTS: int = 3
DEFAULT_MAX_REVIEW_ATTEMPTS: int = 2
DEFAULT_BASE_BRANCH: str = "main"
DEFAULT_VALIDATION_STAGES: tuple[str, ...] = ("format", "lint", "typecheck", "test")
