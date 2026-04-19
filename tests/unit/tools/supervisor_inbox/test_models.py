"""Tests for typed supervisor inbox payload intake models."""

from __future__ import annotations

import pytest

from maverick.tools.supervisor_inbox.models import (
    SubmitAnalysisPayload,
    SubmitFlightPlanPayload,
    SubmitReviewPayload,
    SubmitScopePayload,
    dump_supervisor_payload,
    parse_supervisor_tool_payload,
)


def test_submit_scope_normalizes_legacy_aliases() -> None:
    payload = parse_supervisor_tool_payload(
        "submit_scope",
        {
            "in_scope": ["cli"],
            "out_of_scope_items": ["tui"],
            "scope_rationale": "Keep this change narrow.",
            "boundaries": ["docs only"],
        },
    )

    assert isinstance(payload, SubmitScopePayload)
    assert payload.in_scope == ("cli",)
    assert payload.out_scope == ("tui",)
    assert payload.summary == "Keep this change narrow."
    assert payload.scope_rationale == "Keep this change narrow."
    assert dump_supervisor_payload(payload)["out_scope"] == ["tui"]


def test_submit_analysis_normalizes_legacy_aliases() -> None:
    payload = parse_supervisor_tool_payload(
        "submit_analysis",
        {
            "relevant_modules": ["src/maverick/main.py"],
            "existing_patterns": ["Click commands"],
            "integration_points": ["Step executor"],
            "complexity_assessment": "Low",
        },
    )

    assert isinstance(payload, SubmitAnalysisPayload)
    assert payload.modules == ("src/maverick/main.py",)
    assert payload.patterns == ("Click commands",)
    assert payload.dependencies == ("Step executor",)
    assert payload.complexity_assessment == "Low"


def test_submit_review_normalizes_message_alias_and_derives_count() -> None:
    payload = parse_supervisor_tool_payload(
        "submit_review",
        {
            "approved": False,
            "findings": [
                {
                    "severity": "major",
                    "message": "Missing regression test coverage.",
                    "file": "tests/unit/example.py",
                }
            ],
        },
    )

    assert isinstance(payload, SubmitReviewPayload)
    assert payload.approved is False
    assert payload.effective_findings_count == 1
    assert payload.findings[0].issue == "Missing regression test coverage."

    dumped = dump_supervisor_payload(payload)
    assert dumped["findings"][0]["issue"] == "Missing regression test coverage."


def test_submit_flight_plan_preserves_optional_fields() -> None:
    payload = parse_supervisor_tool_payload(
        "submit_flight_plan",
        {
            "objective": "Ship typed inbox parsing",
            "context": "Mailbox payloads are MCP-validated.",
            "success_criteria": [
                {
                    "description": "Supervisors validate payloads immediately",
                    "verification": "Unit tests cover alias normalization",
                }
            ],
            "in_scope": ["plan", "refuel", "fly"],
            "out_of_scope": ["agent text output schemas"],
            "boundaries": ["Keep MCP tool contract unchanged"],
            "constraints": ["Preserve legacy aliases"],
            "tags": ["architecture", "mcp"],
            "notes": "Do not drop additional properties.",
            "name": "typed-mailbox-intake",
            "version": "2",
        },
    )

    assert isinstance(payload, SubmitFlightPlanPayload)
    assert payload.boundaries == ("Keep MCP tool contract unchanged",)
    assert payload.success_criteria[0].verification == "Unit tests cover alias normalization"
    assert dump_supervisor_payload(payload)["name"] == "typed-mailbox-intake"


def test_unknown_tool_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown supervisor inbox tool"):
        parse_supervisor_tool_payload("submit_not_real", {"ok": True})
