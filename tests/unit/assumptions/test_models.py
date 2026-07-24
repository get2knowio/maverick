"""Tests for maverick.assumptions.models."""

from __future__ import annotations

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_LABELS,
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
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    PerSpecAssumptionCounts,
    Severity,
    coerce_severity,
    nnn_prefix,
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
