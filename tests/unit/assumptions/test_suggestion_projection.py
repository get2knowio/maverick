"""Tests for the suggestion projection surface (055-learned-assumption-resolution,
User Story 2, T012).

Covers data-model.md's ``Suggestion`` dataclass (bd state key
``assumption_suggestion``, one JSON-encoded value — research R4),
``report_entry_from_details``'s parsing of ``KEY_SUGGESTION``/``KEY_AUTO_RESOLVED``
into ``AssumptionReportEntry.suggestion``/``.auto_resolved``, ``entry_to_dict``'s
additive ``"suggestion"``/``"auto_resolved"`` keys (contracts/entry-row-suggestion.md),
``_annotations``'s new ``"auto-resolved"`` tag, the land report's ``_entry_to_dict``
alias picking both up unchanged, and invariant 5 (FR-013/FR-019): the land gate's
``classify()``/``frontier()`` treat a suggestion-carrying open entry identically to
a plain open entry.

Naming contract shared with the parallel T011 suite
(``tests/unit/assumptions/test_suggestions.py``, ``evaluate_suggestion``): the
``Suggestion`` dataclass lives in ``maverick.assumptions.models`` with fields
``resolution: str``, ``resolution_type: Literal["answered", "waived"]``,
``source_entry_id: str``, ``source_spec: str``, ``resolved_at: str``,
``confidence: float``, ``computed_at: str`` (data-model.md field/JSON-key table —
JSON keys are identical to the field names, no aliasing). Encode/decode helpers,
also in ``models.py``: ``suggestion_to_json(suggestion: Suggestion) -> str`` and
``suggestion_from_json(raw: str) -> Suggestion | None`` (returns ``None`` on any
unparseable/malformed input — R11, never raises).
"""

from __future__ import annotations

import json
from unittest.mock import patch

from maverick.assumptions.land_report import _entry_to_dict, classify, frontier
from maverick.assumptions.ledger import report_entry_from_details
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_AUTO_RESOLVED,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_STATUS,
    KEY_SUGGESTION,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    LandVerification,
    Severity,
    Suggestion,
    suggestion_from_json,
    suggestion_to_json,
)
from maverick.assumptions.serialize import _annotations, entry_to_dict
from maverick.beads.models import BeadDetails

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SAMPLE_SUGGESTION_KWARGS: dict[str, object] = {
    "resolution": "Yes — AsyncRetrying, 3 attempts",
    "resolution_type": "answered",
    "source_entry_id": "mv-142",
    "source_spec": "052-conditional-landing",
    "resolved_at": "2026-08-06T14:03:22+00:00",
    "confidence": 0.87,
    "computed_at": "2026-08-07T10:11:12+00:00",
}


def _sample_suggestion(**overrides: object) -> Suggestion:
    kwargs = dict(_SAMPLE_SUGGESTION_KWARGS)
    kwargs.update(overrides)
    return Suggestion(**kwargs)  # type: ignore[arg-type]


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
    is_legacy: bool = False,
    owner_spec: str = "053-assumption-review-console",
    pending_reconcile: bool = False,
    suggestion: Suggestion | None = None,
    auto_resolved: bool = False,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=_record(
            bead_id=bead_id,
            status=status,
            severity=severity,
            is_legacy=is_legacy,
            owner_spec=owner_spec,
        ),
        final_answer="Yes." if status == STATUS_ANSWERED else None,
        waived_by="alice" if status == STATUS_WAIVED else None,
        waived_at="2026-07-24T14:00:00Z" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
        suggestion=suggestion,
        auto_resolved=auto_resolved,
    )


def _bead_details(
    bead_id: str = "dea-9",
    *,
    status: str = STATUS_OPEN,
    severity: str = "medium",
    bd_status: str | None = None,
    owner_spec: str = "052-conditional-landing",
    extra_state: dict[str, str] | None = None,
) -> BeadDetails:
    """Mirrors ``test_ledger_frontier.py``'s ``_entry`` helper (a real
    ``BeadDetails`` — ``report_entry_from_details`` takes duck-typed
    objects, but the codebase's convention is to exercise it against the
    real bd response model)."""
    state = {KEY_SEVERITY: severity, KEY_STATUS: status, KEY_OWNER_SPEC: owner_spec}
    if extra_state:
        state.update(extra_state)
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description="## Question\n\nQ?\n\n## Adopted Answer\n\nOriginal answer.\n\n",
        bead_type="task",
        status=bd_status or ("closed" if status != STATUS_OPEN else "open"),
        labels=[ASSUMPTION_LABEL],
        state=state,
    )


def _legacy_bead_details(bead_id: str = "legacy-1", *, bd_status: str = "open") -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Review: legacy",
        description="legacy escalation",
        bead_type="task",
        status=bd_status,
        labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state={"source_bead": "b-1", "flight_plan": "legacy-plan"},
    )


# ---------------------------------------------------------------------------
# 1. Suggestion JSON round-trip
# ---------------------------------------------------------------------------


class TestSuggestionJsonRoundTrip:
    def test_encode_produces_compact_short_key_json(self) -> None:
        """``suggestion_to_json`` is bd's internal storage wire format, not
        the public contract shape — it uses abbreviated keys and compact
        separators to stay well under bd's ~233-char state-value length
        budget for this key (see research.md R4 addendum and
        ``suggestions._MAX_SUGGESTION_JSON_LENGTH``). The full-field-name
        shape lives only in ``entry_to_dict``'s projection, exercised
        separately below (``TestEntryToDictSuggestionProjection``) — that
        surface is untouched by this wire-format change."""
        suggestion = _sample_suggestion()
        raw = suggestion_to_json(suggestion)
        assert isinstance(raw, str)
        assert raw == json.dumps(json.loads(raw), separators=(",", ":")), (
            "compact JSON separators — no space after ',' or ':'"
        )
        decoded = json.loads(raw)
        assert decoded == {
            "r": _SAMPLE_SUGGESTION_KWARGS["resolution"],
            "rt": _SAMPLE_SUGGESTION_KWARGS["resolution_type"],
            "sid": _SAMPLE_SUGGESTION_KWARGS["source_entry_id"],
            "ss": _SAMPLE_SUGGESTION_KWARGS["source_spec"],
            "ra": _SAMPLE_SUGGESTION_KWARGS["resolved_at"],
            "c": _SAMPLE_SUGGESTION_KWARGS["confidence"],
            "ca": _SAMPLE_SUGGESTION_KWARGS["computed_at"],
        }

    def test_encode_fixed_overhead_stays_well_under_bd_length_budget(self) -> None:
        """Fixed overhead (empty ``resolution``) must stay comfortably under
        bd's observed ~233-char truncation boundary for this state key, so
        real resolution text still has usable budget."""
        raw = suggestion_to_json(_sample_suggestion(resolution=""))
        assert len(raw) < 160

    def test_round_trip_equality(self) -> None:
        suggestion = _sample_suggestion()
        raw = suggestion_to_json(suggestion)
        restored = suggestion_from_json(raw)
        assert restored == suggestion

    def test_round_trip_preserves_confidence_as_float(self) -> None:
        suggestion = _sample_suggestion(confidence=0.756)
        restored = suggestion_from_json(suggestion_to_json(suggestion))
        assert restored is not None
        assert restored.confidence == 0.756

    def test_decode_invalid_json_returns_none(self) -> None:
        assert suggestion_from_json("not json") is None

    def test_decode_truncated_json_returns_none(self) -> None:
        raw = suggestion_to_json(_sample_suggestion())
        assert suggestion_from_json(raw[: len(raw) // 2]) is None

    def test_decode_non_object_json_returns_none(self) -> None:
        assert suggestion_from_json(json.dumps(["not", "an", "object"])) is None

    def test_decode_missing_required_field_returns_none(self) -> None:
        incomplete = dict(_SAMPLE_SUGGESTION_KWARGS)
        del incomplete["confidence"]
        assert suggestion_from_json(json.dumps(incomplete)) is None

    def test_decode_empty_string_returns_none(self) -> None:
        assert suggestion_from_json("") is None


# ---------------------------------------------------------------------------
# 2/3. report_entry_from_details parsing (+ degrade-on-unparseable)
# ---------------------------------------------------------------------------


class TestReportEntryFromDetailsSuggestionParsing:
    def test_parses_valid_suggestion_json(self) -> None:
        suggestion = _sample_suggestion()
        details = _bead_details(extra_state={KEY_SUGGESTION: suggestion_to_json(suggestion)})
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.suggestion == suggestion

    def test_parses_auto_resolved_true(self) -> None:
        details = _bead_details(extra_state={KEY_AUTO_RESOLVED: "true"})
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.auto_resolved is True

    def test_auto_resolved_false_when_key_absent(self) -> None:
        details = _bead_details()
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.auto_resolved is False

    def test_auto_resolved_false_when_key_not_literal_true(self) -> None:
        details = _bead_details(extra_state={KEY_AUTO_RESOLVED: "false"})
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.auto_resolved is False

    def test_suggestion_none_when_key_absent(self) -> None:
        details = _bead_details()
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.suggestion is None

    def test_unparseable_suggestion_degrades_to_none(self) -> None:
        details = _bead_details(extra_state={KEY_SUGGESTION: "not json"})
        with patch("maverick.assumptions.ledger.logger") as mock_logger:
            entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.suggestion is None
        assert mock_logger.debug.called

    def test_legacy_entry_suggestion_and_auto_resolved_always_default(self) -> None:
        """Legacy escalation beads never carry ledger state — both new
        fields must stay at their defaults regardless of arbitrary state
        keys on the bead (legacy beads predate this feature)."""
        details = _legacy_bead_details()
        entry = report_entry_from_details(details)
        assert entry is not None
        assert entry.record.is_legacy is True
        assert entry.suggestion is None
        assert entry.auto_resolved is False


# ---------------------------------------------------------------------------
# 4. entry_to_dict projection
# ---------------------------------------------------------------------------


class TestEntryToDictSuggestionProjection:
    def test_suggestion_dict_shape_when_present(self) -> None:
        suggestion = _sample_suggestion()
        entry = _entry(suggestion=suggestion)
        row = entry_to_dict(entry)
        assert row["suggestion"] == _SAMPLE_SUGGESTION_KWARGS

    def test_suggestion_null_when_absent(self) -> None:
        entry = _entry(suggestion=None)
        row = entry_to_dict(entry)
        assert row["suggestion"] is None

    def test_auto_resolved_true_in_row(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True)
        row = entry_to_dict(entry)
        assert row["auto_resolved"] is True

    def test_auto_resolved_false_in_row(self) -> None:
        entry = _entry()
        row = entry_to_dict(entry)
        assert row["auto_resolved"] is False


# ---------------------------------------------------------------------------
# 5. _annotations gains "auto-resolved"
# ---------------------------------------------------------------------------


class TestAnnotationsAutoResolved:
    def test_auto_resolved_annotation_present(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True)
        tags = _annotations(entry)
        assert "auto-resolved" in tags

    def test_auto_resolved_annotation_absent_when_false(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=False)
        tags = _annotations(entry)
        assert "auto-resolved" not in tags

    def test_auto_resolved_annotation_alongside_legacy(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True, is_legacy=True)
        tags = _annotations(entry)
        assert "auto-resolved" in tags
        assert "legacy" in tags

    def test_entry_to_dict_annotations_list_includes_auto_resolved(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True)
        row = entry_to_dict(entry)
        assert "auto-resolved" in row["annotations"]


# ---------------------------------------------------------------------------
# 6. land_report._entry_to_dict alias picks up the new keys unchanged
# ---------------------------------------------------------------------------


class TestLandReportAliasPicksUpNewKeys:
    def test_alias_includes_suggestion_key(self) -> None:
        suggestion = _sample_suggestion()
        entry = _entry(suggestion=suggestion)
        row = _entry_to_dict(entry)
        assert row["suggestion"] == _SAMPLE_SUGGESTION_KWARGS

    def test_alias_includes_auto_resolved_key(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True)
        row = _entry_to_dict(entry)
        assert row["auto_resolved"] is True

    def test_alias_matches_entry_to_dict_exactly(self) -> None:
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True, suggestion=_sample_suggestion())
        assert _entry_to_dict(entry) == entry_to_dict(entry)


# ---------------------------------------------------------------------------
# 7. FR-013/FR-019 guard: suggestion presence never changes gate behavior
# ---------------------------------------------------------------------------


class TestFR013SuggestionDoesNotAffectLandGate:
    def test_open_entry_with_suggestion_still_blocks_landing(self) -> None:
        entry = _entry(status=STATUS_OPEN, suggestion=_sample_suggestion())
        assert entry.record.status == STATUS_OPEN
        assert entry.blocks_landing is True

    def test_frontier_treats_suggestion_carrying_open_entry_identically(self) -> None:
        plain_open = _entry(bead_id="dea-plain", status=STATUS_OPEN, suggestion=None)
        suggested_open = _entry(
            bead_id="dea-suggested", status=STATUS_OPEN, suggestion=_sample_suggestion()
        )
        result = frontier((plain_open, suggested_open))
        assert {e.record.bead_id for e in result.open_entries} == {"dea-plain", "dea-suggested"}
        assert result.pending_reconcile_entries == ()

    def test_classify_blocked_identically_with_or_without_suggestion(self) -> None:
        plain_open = _entry(bead_id="dea-plain", status=STATUS_OPEN, suggestion=None)
        suggested_open = _entry(
            bead_id="dea-suggested", status=STATUS_OPEN, suggestion=_sample_suggestion()
        )
        assert classify((plain_open,)) == LandVerification.BLOCKED
        assert classify((suggested_open,)) == LandVerification.BLOCKED

    def test_classify_conditionally_verified_for_auto_resolved_waived_entry(self) -> None:
        """Invariant 5: an auto-resolved entry is an ordinary waived entry
        to classify() — no special-casing."""
        entry = _entry(status=STATUS_WAIVED, auto_resolved=True, suggestion=_sample_suggestion())
        assert classify((entry,)) == LandVerification.CONDITIONALLY_VERIFIED
