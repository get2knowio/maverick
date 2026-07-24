"""Tests for the reconcile structured-output payloads (spec 051).

Covers ``SubmitCorrectionPayload``, ``SubmitConflictResolutionPayload``,
``SemanticFinding``, and ``SubmitSemanticDependentsPayload`` — construction,
cross-field validation, and registration in
``SUPERVISOR_TOOL_PAYLOAD_MODELS``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.payloads import (
    SemanticFinding,
    SubmitConflictResolutionPayload,
    SubmitCorrectionPayload,
    SubmitSemanticDependentsPayload,
    dump_supervisor_payload,
    parse_supervisor_tool_payload,
)


class TestSubmitCorrectionPayload:
    def test_valid_construction_with_files_touched(self) -> None:
        payload = SubmitCorrectionPayload(
            summary="Updated the retry budget to match the new answer.",
            files_touched=["src/maverick/workflows/reconcile/models.py"],
        )
        assert payload.summary == "Updated the retry budget to match the new answer."
        assert payload.files_touched == ("src/maverick/workflows/reconcile/models.py",)
        assert payload.no_change_required is False

    def test_no_change_required_with_empty_files_touched_is_valid(self) -> None:
        payload = SubmitCorrectionPayload(
            summary="Already matches the new answer; no edit needed.",
            no_change_required=True,
        )
        assert payload.no_change_required is True
        assert payload.files_touched == ()

    def test_no_change_required_with_nonempty_files_touched_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no_change_required"):
            SubmitCorrectionPayload(
                summary="Contradicts itself.",
                files_touched=["a.py"],
                no_change_required=True,
            )

    def test_summary_requires_min_length(self) -> None:
        with pytest.raises(ValidationError):
            SubmitCorrectionPayload(summary="")


class TestSubmitConflictResolutionPayload:
    def test_valid_construction(self) -> None:
        payload = SubmitConflictResolutionPayload(
            resolved_files=["a.py", "b.py"],
            unresolvable=["c.py"],
            notes="c.py needs a human decision.",
        )
        assert payload.resolved_files == ("a.py", "b.py")
        assert payload.unresolvable == ("c.py",)
        assert payload.notes == "c.py needs a human decision."

    def test_defaults_are_empty(self) -> None:
        payload = SubmitConflictResolutionPayload()
        assert payload.resolved_files == ()
        assert payload.unresolvable == ()
        assert payload.notes == ""


class TestSemanticFinding:
    def test_valid_construction_not_dependent(self) -> None:
        finding = SemanticFinding(change_id="abc123", dependent=False)
        assert finding.change_id == "abc123"
        assert finding.dependent is False
        assert finding.fix_instructions == ""

    def test_valid_construction_dependent_with_fix_instructions(self) -> None:
        finding = SemanticFinding(
            change_id="abc123",
            dependent=True,
            reason="Uses the old per-bead retry assumption.",
            fix_instructions="Update the loop to retry per-run instead of per-bead.",
        )
        assert finding.dependent is True
        assert finding.fix_instructions == "Update the loop to retry per-run instead of per-bead."

    def test_dependent_with_empty_fix_instructions_rejected(self) -> None:
        with pytest.raises(ValidationError, match="fix_instructions"):
            SemanticFinding(change_id="abc123", dependent=True)

    def test_dependent_with_whitespace_only_fix_instructions_rejected(self) -> None:
        with pytest.raises(ValidationError, match="fix_instructions"):
            SemanticFinding(change_id="abc123", dependent=True, fix_instructions="   ")


class TestSubmitSemanticDependentsPayload:
    def test_valid_construction(self) -> None:
        payload = SubmitSemanticDependentsPayload(
            findings=[
                {"change_id": "abc123", "dependent": False},
                {
                    "change_id": "def456",
                    "dependent": True,
                    "fix_instructions": "Rename the field.",
                },
            ]
        )
        assert len(payload.findings) == 2
        assert payload.findings[0].change_id == "abc123"
        assert payload.findings[1].dependent is True

    def test_defaults_to_empty_findings(self) -> None:
        payload = SubmitSemanticDependentsPayload()
        assert payload.findings == ()

    def test_invalid_nested_finding_fails_whole_payload(self) -> None:
        with pytest.raises(ValidationError, match="fix_instructions"):
            SubmitSemanticDependentsPayload(findings=[{"change_id": "abc123", "dependent": True}])


class TestSupervisorToolRegistration:
    def test_submit_correction_round_trips(self) -> None:
        payload = parse_supervisor_tool_payload(
            "submit_correction",
            {
                "summary": "Corrected the retry budget wording.",
                "files_touched": ["src/a.py"],
                "no_change_required": False,
            },
        )
        assert isinstance(payload, SubmitCorrectionPayload)
        dumped = dump_supervisor_payload(payload)
        assert dumped["summary"] == "Corrected the retry budget wording."
        assert dumped["files_touched"] == ["src/a.py"]

    def test_submit_conflict_resolution_round_trips(self) -> None:
        payload = parse_supervisor_tool_payload(
            "submit_conflict_resolution",
            {
                "resolved_files": ["a.py"],
                "unresolvable": [],
                "notes": "All clear.",
            },
        )
        assert isinstance(payload, SubmitConflictResolutionPayload)
        dumped = dump_supervisor_payload(payload)
        assert dumped["resolved_files"] == ["a.py"]
        assert dumped["notes"] == "All clear."

    def test_submit_semantic_dependents_round_trips(self) -> None:
        payload = parse_supervisor_tool_payload(
            "submit_semantic_dependents",
            {
                "findings": [
                    {
                        "change_id": "abc123",
                        "dependent": True,
                        "reason": "Depends on the old answer.",
                        "fix_instructions": "Update the assertion.",
                    }
                ]
            },
        )
        assert isinstance(payload, SubmitSemanticDependentsPayload)
        dumped = dump_supervisor_payload(payload)
        assert dumped["findings"][0]["change_id"] == "abc123"
        assert dumped["findings"][0]["fix_instructions"] == "Update the assertion."
