"""Constants for FlyBeadsWorkflow."""

from __future__ import annotations

# Step names
PREFLIGHT = "preflight"
SNAPSHOT_UNCOMMITTED = "snapshot_uncommitted"
SELECT_BEAD = "select_bead"
IMPLEMENT_AND_VALIDATE = "implement_and_validate"
GATE_CHECK = "gate_check"
GATE_REMEDIATION = "gate_remediation"
REVIEW = "review"
COMMIT = "commit"
RECORD_RUNWAY = "record_runway"
BASELINE_GATE = "baseline_gate"
ACCEPTANCE_CHECK = "acceptance_check"
SPEC_COMPLIANCE = "spec_compliance"

# Default config values
# 0 = unlimited (drain the queue until no ready beads remain). Refuel
# routinely produces 40+ beads per epic, so a hard cap surprises users
# who expect ``--epic <id>`` to drain the epic. Pass ``--max-beads N``
# explicitly when you want a bounded run.
MAX_BEADS: int = 0
WORKFLOW_NAME: str = "fly-beads"

# Bead execution defaults
DEFAULT_VALIDATION_STAGES: tuple[str, ...] = ("format", "lint", "typecheck", "test")

# Per-bead retry limit.  After this many failed attempts on a single bead,
# the bead is deferred and the workflow moves on to the next one.
MAX_RETRIES_PER_BEAD: int = 3

# Maximum depth of the discovered-from escalation chain.  After this many
# tiers of follow-up beads, the chain is committed as-is and tagged for
# human review instead of creating further follow-ups.
MAX_ESCALATION_DEPTH: int = 3
