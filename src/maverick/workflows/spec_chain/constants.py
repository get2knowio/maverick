"""Constants for the spec-chain workflow (`maverick spec`).

Step ordering, bead/ledger labels and state keys, and timeouts shared
across the ``spec_chain`` package. See specs/050-headless-spec-chain/
data-model.md and contracts/ledger-and-beads.md for the authoritative
contract.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CHAIN_STEP_ORDER",
    "KEY_ADOPTED_BY_EPIC",
    "KEY_FINDING_FINGERPRINT",
    "KEY_REMEDIATION_SOURCE",
    "KEY_SOURCE_REF",
    "KEY_SPECKIT_FEATURE",
    "REMEDIATION_SOURCE_ANALYZE",
    "SOURCE_REF_ASSUMPTIONS",
    "SOURCE_REF_CLARIFY",
    "SPEC_REMEDIATION_LABEL",
    "STEP_TIMEOUT_SECONDS",
    "WORKSPACE_OP_TIMEOUT_SECONDS",
    "ChainStep",
]


class ChainStep(StrEnum):
    """Ordered spec-chain steps.

    Order is the single source of truth for FR-002/FR-008 gating — see
    :data:`CHAIN_STEP_ORDER`.
    """

    SPECIFY = "specify"
    CLARIFY = "clarify"
    PLAN = "plan"
    TASKS = "tasks"
    ANALYZE = "analyze"


#: Strict execution order (FR-002). ``next_step()`` in ``models.py``
#: derives the step to run next from this tuple.
CHAIN_STEP_ORDER: tuple[ChainStep, ...] = (
    ChainStep.SPECIFY,
    ChainStep.CLARIFY,
    ChainStep.PLAN,
    ChainStep.TASKS,
    ChainStep.ANALYZE,
)

#: Remediation bead label (analyze findings -> standalone beads, R6).
SPEC_REMEDIATION_LABEL = "spec-remediation"

#: ``remediation_source`` state-key value stamped on remediation beads.
REMEDIATION_SOURCE_ANALYZE = "spec-chain:analyze"

#: Remediation-bead state keys (contracts/ledger-and-beads.md).
KEY_SPECKIT_FEATURE = "speckit_feature"
KEY_REMEDIATION_SOURCE = "remediation_source"
KEY_FINDING_FINGERPRINT = "finding_fingerprint"

#: Adoption stamp (R6 fallback — no `bd update --parent` primitive exists;
#: see research.md R6). Set alongside the DISCOVERED_FROM dependency edge
#: when `refuel --speckit` adopts a standalone remediation bead under its
#: epic; also the idempotency check for "already adopted".
KEY_ADOPTED_BY_EPIC = "adopted_by_epic"

#: Standalone ledger-entry state key (R5) — replaces ``source_bead`` when
#: the chain files a clarify decision with no owning epic yet.
KEY_SOURCE_REF = "source_ref"

#: ``source_ref`` value stamped on clarify-derived ledger entries.
SOURCE_REF_CLARIFY = "spec-chain:clarify"

#: Provenance for entries harvested from specify's ``## Assumptions``
#: section, distinct from clarify's own answers so a reviewer can tell
#: "the model was asked and answered" from "the model decided unasked".
SOURCE_REF_ASSUMPTIONS = "spec-chain:assumptions"

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

#: Per-step airframe ``execute()`` timeout — chain steps synthesize or
#: parse full markdown artifacts and can run for several minutes.
STEP_TIMEOUT_SECONDS: float = 1200.0

#: Deterministic-op timeout — workspace create/forget, artifact landing.
WORKSPACE_OP_TIMEOUT_SECONDS: float = 60.0
