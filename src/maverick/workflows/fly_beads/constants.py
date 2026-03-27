"""Constants for FlyBeadsWorkflow."""

from __future__ import annotations

# Step names
PREFLIGHT = "preflight"
SNAPSHOT_UNCOMMITTED = "snapshot_uncommitted"
CREATE_WORKSPACE = "create_workspace"
SELECT_BEAD = "select_bead"
IMPLEMENT_AND_VALIDATE = "implement_and_validate"
GATE_CHECK = "gate_check"
GATE_REMEDIATION = "gate_remediation"
REVIEW = "review"
COMMIT = "commit"
RECORD_RUNWAY = "record_runway"

# Default config values
MAX_BEADS: int = 30
WORKFLOW_NAME: str = "fly-beads"

# Timeouts (seconds)
IMPLEMENT_AND_VALIDATE_TIMEOUT: int = 900  # 15 min — agent implements + validates
GATE_TIMEOUT: int = 300  # 5 min — orchestrator's independent validation
GATE_REMEDIATION_TIMEOUT: int = 600  # 10 min — remediation agent fixes gate failures

# Bead execution defaults
DEFAULT_BASE_BRANCH: str = "main"
DEFAULT_VALIDATION_STAGES: tuple[str, ...] = ("format", "lint", "typecheck", "test")

# Per-bead retry limit.  After this many failed attempts on a single bead,
# the bead is deferred and the workflow moves on to the next one.
MAX_RETRIES_PER_BEAD: int = 3

# Maximum depth of the discovered-from escalation chain.  After this many
# tiers of follow-up beads, the chain is committed as-is and tagged for
# human review instead of creating further follow-ups.
MAX_ESCALATION_DEPTH: int = 3

# If this many consecutive review attempts across the escalation chain
# show no improvement (issue count not decreasing), fire the circuit breaker.
MAX_NO_IMPROVEMENT_ATTEMPTS: int = 6
