"""Assumption ledger — structured, bd-native tracking of adopted assumptions.

Public API re-exported here; nothing in this package imports workflow or
CLI modules (research R13). See ``specs/049-assumption-ledger/contracts/``.
"""

from __future__ import annotations

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_LABELS,
    ASSUMPTION_REVIEW_LABEL,
    DEFAULT_SEVERITY,
    EPIC_KEY_FLIGHT_PLAN_NAME,
    EPIC_KEY_SPECKIT_FEATURE,
    KEY_ANSWER,
    KEY_CHANGE_IDS,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    PerSpecAssumptionCounts,
    Severity,
    StampResult,
    coerce_severity,
    nnn_prefix,
)

__all__ = [
    "ASSUMPTION_LABEL",
    "ASSUMPTION_LABELS",
    "ASSUMPTION_REVIEW_LABEL",
    "DEFAULT_SEVERITY",
    "EPIC_KEY_FLIGHT_PLAN_NAME",
    "EPIC_KEY_SPECKIT_FEATURE",
    "KEY_ANSWER",
    "KEY_CHANGE_IDS",
    "KEY_OWNER_SPEC",
    "KEY_SEVERITY",
    "KEY_SEVERITY_DEFAULTED",
    "KEY_SOURCE_BEAD",
    "KEY_STATUS",
    "KEY_WAIVE_REASON",
    "KEY_WAIVED_AT",
    "KEY_WAIVED_BY",
    "NEEDS_HUMAN_REVIEW_LABEL",
    "STATUS_ANSWERED",
    "STATUS_OPEN",
    "STATUS_WAIVED",
    "AssumptionLedgerError",
    "AssumptionRecord",
    "PerSpecAssumptionCounts",
    "Severity",
    "StampResult",
    "coerce_severity",
    "nnn_prefix",
]
