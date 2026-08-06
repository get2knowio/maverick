"""Tests for maverick.assumptions.models."""

from __future__ import annotations

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_LABELS,
    KEY_ANSWER,
    KEY_CHANGE_IDS,
    KEY_OWNER_SPEC,
    KEY_RECONCILE_CHANGE_ID,
    KEY_RECONCILE_REASON,
    KEY_RECONCILE_STATUS,
    KEY_RECONCILED_ANSWER,
    KEY_RECONCILED_AT,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    RECONCILE_STATUS_NEEDS_REVIEW,
    RECONCILE_STATUS_PENDING,
    RECONCILE_STATUS_RECONCILED,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    TERMINAL_RECONCILE_STATUSES,
    AssumptionRecord,
    AssumptionReportEntry,
    LandFrontier,
    LandVerification,
    PerSpecAssumptionCounts,
    Severity,
    coerce_severity,
    nnn_prefix,
    normalize_answer,
)


class TestSeverity:
    def test_members(self) -> None:
        assert Severity.LOW == "low"
        assert Severity.MEDIUM == "medium"
        assert Severity.HIGH == "high"


class TestCoerceSeverity:
    def test_valid_values_pass_through(self) -> None:
        for value in ("low", "medium", "high"):
            severity, defaulted = coerce_severity(value)
            assert severity == Severity(value)
            assert defaulted is False

    def test_invalid_value_defaults_to_medium(self) -> None:
        severity, defaulted = coerce_severity("urgent")
        assert severity == Severity.MEDIUM
        assert defaulted is True

    def test_none_defaults_to_medium(self) -> None:
        severity, defaulted = coerce_severity(None)
        assert severity == Severity.MEDIUM
        assert defaulted is True


class TestNnnPrefix:
    def test_extracts_leading_prefix(self) -> None:
        assert nnn_prefix("049-assumption-ledger") == 49
        assert nnn_prefix("001-greet-cli") == 1

    def test_none_when_no_prefix(self) -> None:
        assert nnn_prefix("my-flight-plan") is None
        assert nnn_prefix("") is None


class TestAssumptionRecord:
    def test_construction(self) -> None:
        record = AssumptionRecord(
            bead_id="dea-1",
            question="Q?",
            adopted_answer="A.",
            alternatives=("B.",),
            severity=Severity.HIGH,
            severity_defaulted=False,
            status=STATUS_OPEN,
            owner_spec="049-assumption-ledger",
            source_bead="dea-0",
            change_ids=(),
            is_legacy=False,
        )
        assert record.bead_id == "dea-1"
        assert record.change_ids == ()
        assert record.is_legacy is False
        assert record.created_at is None

    def test_created_at_carries_bd_timestamp(self) -> None:
        record = AssumptionRecord(
            bead_id="dea-1",
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=Severity.MEDIUM,
            severity_defaulted=False,
            status=STATUS_OPEN,
            owner_spec="054-assumption-batch-scheduler",
            source_bead="dea-0",
            change_ids=(),
            is_legacy=False,
            created_at="2026-08-05T22:09:49Z",
        )
        assert record.created_at == "2026-08-05T22:09:49Z"


class TestPerSpecAssumptionCounts:
    def test_construction(self) -> None:
        counts = PerSpecAssumptionCounts(
            owner_spec="049-assumption-ledger",
            open={Severity.LOW: 1, Severity.MEDIUM: 0, Severity.HIGH: 0},
            answered={Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 0},
            waived={Severity.LOW: 0, Severity.MEDIUM: 0, Severity.HIGH: 1},
            legacy_open=2,
        )
        assert counts.open[Severity.LOW] == 1
        assert counts.legacy_open == 2


class TestConstants:
    def test_state_key_constants_are_distinct_strings(self) -> None:
        keys = {
            KEY_SEVERITY,
            KEY_SEVERITY_DEFAULTED,
            KEY_STATUS,
            KEY_OWNER_SPEC,
            KEY_CHANGE_IDS,
            KEY_ANSWER,
            KEY_WAIVED_BY,
            KEY_WAIVED_AT,
            KEY_WAIVE_REASON,
            KEY_SOURCE_BEAD,
        }
        assert len(keys) == 10
        assert all(isinstance(k, str) and k for k in keys)

    def test_status_values(self) -> None:
        assert {STATUS_OPEN, STATUS_ANSWERED, STATUS_WAIVED} == {
            "open",
            "answered",
            "waived",
        }

    def test_assumption_labels_include_legacy(self) -> None:
        assert ASSUMPTION_LABEL in ASSUMPTION_LABELS
        assert "assumption-review" in ASSUMPTION_LABELS
        assert "needs-human-review" in ASSUMPTION_LABELS


class TestReconcileConstants:
    """New bd state keys and status values for reconcile (data-model.md §1)."""

    def test_reconcile_state_key_values(self) -> None:
        assert KEY_RECONCILE_STATUS == "assumption_reconcile_status"
        assert KEY_RECONCILED_AT == "assumption_reconciled_at"
        assert KEY_RECONCILED_ANSWER == "assumption_reconciled_answer"
        assert KEY_RECONCILE_CHANGE_ID == "assumption_reconcile_change_id"
        assert KEY_RECONCILE_REASON == "assumption_reconcile_reason"

    def test_reconcile_state_keys_are_distinct_from_existing_keys(self) -> None:
        existing = {
            KEY_SEVERITY,
            KEY_SEVERITY_DEFAULTED,
            KEY_STATUS,
            KEY_OWNER_SPEC,
            KEY_CHANGE_IDS,
            KEY_ANSWER,
            KEY_WAIVED_BY,
            KEY_WAIVED_AT,
            KEY_WAIVE_REASON,
            KEY_SOURCE_BEAD,
        }
        new_keys = {
            KEY_RECONCILE_STATUS,
            KEY_RECONCILED_AT,
            KEY_RECONCILED_ANSWER,
            KEY_RECONCILE_CHANGE_ID,
            KEY_RECONCILE_REASON,
        }
        assert len(new_keys) == 5
        assert existing.isdisjoint(new_keys)

    def test_reconcile_status_values(self) -> None:
        assert RECONCILE_STATUS_RECONCILED == "reconciled"
        assert RECONCILE_STATUS_NEEDS_REVIEW == "needs-interactive-review"
        assert RECONCILE_STATUS_PENDING == "pending"

    def test_pending_sentinel_is_non_terminal(self) -> None:
        # bd rejects empty state values, so re-arm writes ``pending``; it
        # must NOT be treated as terminal or re-answered entries would never
        # be re-detected.
        assert RECONCILE_STATUS_PENDING not in TERMINAL_RECONCILE_STATUSES
        assert {
            RECONCILE_STATUS_RECONCILED,
            RECONCILE_STATUS_NEEDS_REVIEW,
        } == TERMINAL_RECONCILE_STATUSES


class TestNormalizeAnswer:
    def test_collapses_internal_whitespace(self) -> None:
        assert normalize_answer("Foo   Bar\n") == "foo bar"

    def test_casefolds(self) -> None:
        assert normalize_answer("FOO") == "foo"

    def test_matches_across_whitespace_and_case_variants(self) -> None:
        assert normalize_answer("Foo   Bar\n") == normalize_answer("foo bar")

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert normalize_answer("  foo bar  ") == "foo bar"

    def test_empty_string(self) -> None:
        assert normalize_answer("") == ""


def _record(
    *,
    bead_id: str = "dea-1",
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    change_ids: tuple[str, ...] = (),
    is_legacy: bool = False,
) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question="Q?",
        adopted_answer="A.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec="052-conditional-landing",
        source_bead="dea-0",
        change_ids=change_ids,
        is_legacy=is_legacy,
    )


def _entry(
    *,
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    change_ids: tuple[str, ...] = (),
    reconcile_change_id: str | None = None,
    pending_reconcile: bool = False,
    waived_by: str | None = None,
    auto_resolved: bool = False,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=_record(status=status, severity=severity, change_ids=change_ids),
        final_answer=None,
        waived_by=waived_by,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=reconcile_change_id,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
        auto_resolved=auto_resolved,
    )


class TestLandVerification:
    def test_members(self) -> None:
        assert LandVerification.VERIFIED == "verified"
        assert LandVerification.CONDITIONALLY_VERIFIED == "conditionally-verified"
        assert LandVerification.BLOCKED == "blocked"


class TestAssumptionReportEntryBucket:
    def test_waived_status_buckets_waived(self) -> None:
        assert _entry(status=STATUS_WAIVED).bucket == "waived"

    def test_auto_resolved_waived_status_buckets_waived(self) -> None:
        """055 T030 regression/proof: an auto-resolved entry
        (``waived_by="maverick-resolver"``, ``auto_resolved=True``) is an
        ordinary waived entry to ``.bucket`` — no special-casing."""
        entry = _entry(status=STATUS_WAIVED, waived_by="maverick-resolver", auto_resolved=True)
        assert entry.bucket == "waived"

    def test_answered_status_buckets_resolved(self) -> None:
        assert _entry(status=STATUS_ANSWERED).bucket == "resolved"

    def test_open_status_buckets_open(self) -> None:
        assert _entry(status=STATUS_OPEN).bucket == "open"

    def test_legacy_open_bucket_is_open(self) -> None:
        entry = AssumptionReportEntry(
            record=_record(status=STATUS_OPEN, severity=Severity.MEDIUM, is_legacy=True),
            final_answer=None,
            waived_by=None,
            waived_at=None,
            waive_reason=None,
            reconcile_status=None,
            reconciled_answer=None,
            reconcile_change_id=None,
            reconcile_reason=None,
            pending_reconcile=False,
        )
        assert entry.bucket == "open"


class TestAssumptionReportEntryAffectedChangeIds:
    def test_merges_ledger_and_reconcile_change_ids(self) -> None:
        entry = _entry(change_ids=("zzkw",), reconcile_change_id="rlvk")
        assert entry.affected_change_ids == ("zzkw", "rlvk")

    def test_dedups_reconcile_change_id_already_in_ledger_stamps(self) -> None:
        entry = _entry(change_ids=("zzkw", "rlvk"), reconcile_change_id="rlvk")
        assert entry.affected_change_ids == ("zzkw", "rlvk")

    def test_no_reconcile_change_id_returns_ledger_stamps_only(self) -> None:
        entry = _entry(change_ids=("zzkw", "rlvk"))
        assert entry.affected_change_ids == ("zzkw", "rlvk")

    def test_order_preserving(self) -> None:
        entry = _entry(change_ids=("a", "b"), reconcile_change_id="c")
        assert entry.affected_change_ids == ("a", "b", "c")


class TestAssumptionReportEntryBlocksLanding:
    def test_open_low_severity_blocks(self) -> None:
        assert _entry(status=STATUS_OPEN, severity=Severity.LOW).blocks_landing is True

    def test_open_medium_severity_blocks(self) -> None:
        assert _entry(status=STATUS_OPEN, severity=Severity.MEDIUM).blocks_landing is True

    def test_open_high_severity_blocks(self) -> None:
        assert _entry(status=STATUS_OPEN, severity=Severity.HIGH).blocks_landing is True

    def test_answered_and_not_pending_reconcile_does_not_block(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=False)
        assert entry.blocks_landing is False

    def test_answered_and_pending_reconcile_blocks(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        assert entry.blocks_landing is True

    def test_waived_does_not_block(self) -> None:
        assert _entry(status=STATUS_WAIVED).blocks_landing is False


class TestLandFrontier:
    def test_empty_when_both_tuples_empty(self) -> None:
        frontier = LandFrontier(open_entries=(), pending_reconcile_entries=())
        assert frontier.is_empty is True

    def test_not_empty_with_open_entries(self) -> None:
        frontier = LandFrontier(open_entries=(_entry(),), pending_reconcile_entries=())
        assert frontier.is_empty is False

    def test_not_empty_with_pending_reconcile_entries(self) -> None:
        frontier = LandFrontier(
            open_entries=(), pending_reconcile_entries=(_entry(pending_reconcile=True),)
        )
        assert frontier.is_empty is False
