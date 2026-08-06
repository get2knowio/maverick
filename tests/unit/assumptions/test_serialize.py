"""Tests for maverick.assumptions.serialize — the canonical row projection.

Covers data-model.md's ``entry_to_dict(entry) -> dict[str, object]``
(research R4): the same row shape used by both the land report and
``review --list``, extracted from ``land_report._entry_to_dict`` and
extended additively with ``owner_spec``/``status``/``bucket``/
``blocks_landing``. See specs/053-assumption-review-console/data-model.md
"entry_to_dict" for the authoritative key list.
"""

from __future__ import annotations

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.assumptions.serialize import entry_to_dict


def _record(
    *,
    bead_id: str = "dea-1",
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    severity_defaulted: bool = False,
    is_legacy: bool = False,
    owner_spec: str = "053-assumption-review-console",
    source_bead: str = "dea-0",
    change_ids: tuple[str, ...] = (),
    question: str = "Q?",
    adopted_answer: str = "A.",
    alternatives: tuple[str, ...] = (),
    created_at: str | None = None,
) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer=adopted_answer,
        alternatives=alternatives,
        severity=severity,
        severity_defaulted=severity_defaulted,
        status=status,
        owner_spec=owner_spec,
        source_bead=source_bead,
        change_ids=change_ids,
        is_legacy=is_legacy,
        created_at=created_at,
    )


def _entry(
    *,
    bead_id: str = "dea-1",
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    severity_defaulted: bool = False,
    is_legacy: bool = False,
    owner_spec: str = "053-assumption-review-console",
    change_ids: tuple[str, ...] = (),
    pending_reconcile: bool = False,
    reconcile_status: str | None = None,
    reconciled_answer: str | None = None,
    reconcile_change_id: str | None = None,
    reconcile_reason: str | None = None,
    created_at: str | None = None,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=_record(
            bead_id=bead_id,
            status=status,
            severity=severity,
            severity_defaulted=severity_defaulted,
            is_legacy=is_legacy,
            owner_spec=owner_spec,
            change_ids=change_ids,
            created_at=created_at,
        ),
        final_answer="Yes." if status == STATUS_ANSWERED else None,
        waived_by="alice" if status == STATUS_WAIVED else None,
        waived_at="2026-07-24T14:00:00Z" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=reconcile_status,
        reconciled_answer=reconciled_answer,
        reconcile_change_id=reconcile_change_id,
        reconcile_reason=reconcile_reason,
        pending_reconcile=pending_reconcile,
    )


class TestEntryToDictProjection:
    """Field-for-field projection from a built AssumptionReportEntry."""

    def test_record_fields_projected(self) -> None:
        entry = _entry(
            bead_id="dea-42",
            severity=Severity.HIGH,
            severity_defaulted=True,
            is_legacy=True,
        )
        row = entry_to_dict(entry)
        assert row["bead_id"] == "dea-42"
        assert row["question"] == "Q?"
        assert row["adopted_answer"] == "A."
        assert row["severity"] == "high"
        assert row["severity_defaulted"] is True
        assert row["is_legacy"] is True
        assert row["source_bead"] == "dea-0"

    def test_alternatives_is_a_list(self) -> None:
        entry = _entry()
        row = entry_to_dict(entry)
        assert row["alternatives"] == []
        assert isinstance(row["alternatives"], list)

    def test_affected_change_ids_is_a_list(self) -> None:
        entry = _entry(change_ids=("zzkw",))
        row = entry_to_dict(entry)
        assert row["affected_change_ids"] == ["zzkw"]
        assert isinstance(row["affected_change_ids"], list)

    def test_annotations_is_a_list(self) -> None:
        entry = _entry(is_legacy=True, status=STATUS_OPEN)
        row = entry_to_dict(entry)
        assert isinstance(row["annotations"], list)
        assert "legacy" in row["annotations"]

    def test_reconcile_dict_shape(self) -> None:
        entry = _entry(
            status=STATUS_ANSWERED,
            reconcile_status="reconciled",
            reconciled_answer="Final.",
            reconcile_change_id="rlvk",
            reconcile_reason="drifted",
        )
        row = entry_to_dict(entry)
        assert row["reconcile"] == {
            "status": "reconciled",
            "reconciled_answer": "Final.",
            "change_id": "rlvk",
            "reason": "drifted",
        }

    def test_pending_reconcile_bool(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        row = entry_to_dict(entry)
        assert row["pending_reconcile"] is True


class TestEntryToDictNewFields:
    """The three additive fields new in 053: owner_spec, status, bucket,
    blocks_landing."""

    def test_owner_spec_from_record(self) -> None:
        entry = _entry(owner_spec="052-conditional-landing")
        row = entry_to_dict(entry)
        assert row["owner_spec"] == "052-conditional-landing"

    def test_status_from_record(self) -> None:
        entry = _entry(status=STATUS_ANSWERED)
        row = entry_to_dict(entry)
        assert row["status"] == "answered"

    def test_bucket_open(self) -> None:
        entry = _entry(status=STATUS_OPEN)
        row = entry_to_dict(entry)
        assert row["bucket"] == "open"

    def test_bucket_resolved(self) -> None:
        entry = _entry(status=STATUS_ANSWERED)
        row = entry_to_dict(entry)
        assert row["bucket"] == "resolved"

    def test_bucket_waived(self) -> None:
        entry = _entry(status=STATUS_WAIVED)
        row = entry_to_dict(entry)
        assert row["bucket"] == "waived"

    def test_blocks_landing_true_when_open(self) -> None:
        entry = _entry(status=STATUS_OPEN)
        row = entry_to_dict(entry)
        assert row["blocks_landing"] is True

    def test_blocks_landing_true_when_pending_reconcile(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        row = entry_to_dict(entry)
        assert row["blocks_landing"] is True

    def test_blocks_landing_false_when_resolved(self) -> None:
        entry = _entry(status=STATUS_ANSWERED)
        row = entry_to_dict(entry)
        assert row["blocks_landing"] is False

    def test_blocks_landing_false_when_waived(self) -> None:
        entry = _entry(status=STATUS_WAIVED)
        row = entry_to_dict(entry)
        assert row["blocks_landing"] is False


class TestEntryToDictCreatedAt:
    """``created_at`` (spec 054 research R1) — additive, shared with the land report."""

    def test_created_at_present(self) -> None:
        entry = _entry(created_at="2026-08-05T22:09:49Z")
        row = entry_to_dict(entry)
        assert row["created_at"] == "2026-08-05T22:09:49Z"

    def test_created_at_none_when_absent(self) -> None:
        entry = _entry()
        row = entry_to_dict(entry)
        assert row["created_at"] is None


class TestNullOmissionRule:
    """waiver is None unless the entry is in the waived bucket."""

    def test_waiver_none_when_open(self) -> None:
        entry = _entry(status=STATUS_OPEN)
        row = entry_to_dict(entry)
        assert row["waiver"] is None

    def test_waiver_none_when_resolved(self) -> None:
        entry = _entry(status=STATUS_ANSWERED)
        row = entry_to_dict(entry)
        assert row["waiver"] is None

    def test_waiver_present_when_waived(self) -> None:
        entry = _entry(status=STATUS_WAIVED)
        row = entry_to_dict(entry)
        assert row["waiver"] == {
            "by": "alice",
            "at": "2026-07-24T14:00:00Z",
            "reason": "n/a",
        }


class TestEqualityWithLandReportRow:
    """entry_to_dict must not silently diverge from land_report's own
    row projection for the pre-existing keys."""

    _PRE_EXISTING_KEYS = (
        "bead_id",
        "question",
        "adopted_answer",
        "final_answer",
        "alternatives",
        "severity",
        "severity_defaulted",
        "is_legacy",
        "source_bead",
        "affected_change_ids",
        "waiver",
        "reconcile",
        "pending_reconcile",
        "annotations",
        "bucket",
    )

    def test_matches_land_report_private_builder(self) -> None:
        from maverick.assumptions.land_report import _entry_to_dict

        entry = _entry(
            bead_id="dea-7",
            status=STATUS_WAIVED,
            severity=Severity.HIGH,
            is_legacy=True,
            change_ids=("zzkw",),
            reconcile_change_id="rlvk",
        )
        new_row = entry_to_dict(entry)
        legacy_row = _entry_to_dict(entry)
        for key in self._PRE_EXISTING_KEYS:
            assert new_row[key] == legacy_row[key], f"mismatch on key {key!r}"

    def test_full_dict_equality_on_pre_existing_keys(self) -> None:
        from maverick.assumptions.land_report import _entry_to_dict

        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        new_row = entry_to_dict(entry)
        legacy_row = _entry_to_dict(entry)
        filtered_new = {k: v for k, v in new_row.items() if k in self._PRE_EXISTING_KEYS}
        filtered_legacy = {k: v for k, v in legacy_row.items() if k in self._PRE_EXISTING_KEYS}
        assert filtered_new == filtered_legacy
