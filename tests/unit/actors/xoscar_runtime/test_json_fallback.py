"""Tests for the JSON-in-text fallback (FUTURE.md §4.6.1).

Covers the helpers ``_extract_json_candidates`` and
``try_parse_tool_payload_from_text`` plus the parse-and-validate
behaviour against actual mailbox-tool schemas.
"""

from __future__ import annotations

import json

from maverick.actors.xoscar._agentic import (
    _extract_json_candidates,
    try_parse_tool_payload_from_text,
)
from maverick.tools.agent_inbox.models import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)

# ---------------------------------------------------------------------------
# _extract_json_candidates
# ---------------------------------------------------------------------------


def test_extract_returns_empty_for_empty_string() -> None:
    assert _extract_json_candidates("") == []
    assert _extract_json_candidates("   \n  \t") == []


def test_extract_finds_fenced_json_block() -> None:
    text = """Here's my answer:

```json
{"details": [{"id": "wu-1", "instructions": "do it"}]}
```
"""
    candidates = _extract_json_candidates(text)
    assert len(candidates) >= 1
    assert '{"details": [{"id": "wu-1", "instructions": "do it"}]}' in candidates[0]


def test_extract_finds_plain_fenced_block() -> None:
    """Code block without a language tag still works."""
    text = 'Sure:\n```\n{"foo": 1}\n```\n'
    candidates = _extract_json_candidates(text)
    assert any('"foo": 1' in c for c in candidates)


def test_extract_returns_whole_text_as_fallback() -> None:
    """When there's no fence but the whole response is JSON-shaped, it's a candidate."""
    text = '{"details": []}'
    candidates = _extract_json_candidates(text)
    assert text in candidates


def test_extract_prefers_fenced_blocks_over_whole_text() -> None:
    """Fenced blocks should be ordered first (higher priority)."""
    text = '{"top": "level"}\n\n```json\n{"fenced": "block"}\n```\n'
    candidates = _extract_json_candidates(text)
    # Fenced block should appear before the whole-text fallback.
    fenced_idx = next(i for i, c in enumerate(candidates) if "fenced" in c)
    whole_idx = next(i for i, c in enumerate(candidates) if c == text.strip())
    assert fenced_idx < whole_idx


def test_extract_handles_multiple_fenced_blocks() -> None:
    text = """First block:
```json
{"first": true}
```

Second block:
```json
{"second": true}
```
"""
    candidates = _extract_json_candidates(text)
    assert any('"first": true' in c for c in candidates)
    assert any('"second": true' in c for c in candidates)


# ---------------------------------------------------------------------------
# try_parse_tool_payload_from_text — full parse + validate
# ---------------------------------------------------------------------------


def test_parses_submit_details_from_fenced_block() -> None:
    """Happy path: agent missed the tool call but emitted a valid
    SubmitDetailsPayload as a fenced JSON block. We recover it."""
    body = json.dumps(
        {
            "details": [
                {
                    "id": "wu-1",
                    "instructions": "do it",
                    "acceptance_criteria": [{"text": "passes", "trace_ref": "SC-001"}],
                    "verification": ["npm test"],
                    "test_specification": "tests pass",
                }
            ]
        }
    )
    text = f"Sorry, I forgot the tool. Here's the data:\n\n```json\n{body}\n```\n"
    payload = try_parse_tool_payload_from_text(text, "submit_details")
    assert isinstance(payload, SubmitDetailsPayload)
    assert len(payload.details) == 1
    assert payload.details[0].id == "wu-1"


def test_parses_submit_outline_from_plain_text() -> None:
    body = json.dumps(
        {
            "work_units": [
                {"id": "wu-1", "task": "task1", "sequence": 1},
                {"id": "wu-2", "task": "task2", "sequence": 2},
            ]
        }
    )
    payload = try_parse_tool_payload_from_text(body, "submit_outline")
    assert isinstance(payload, SubmitOutlinePayload)
    assert len(payload.work_units) == 2


def test_parses_submit_fix_from_text_with_prefix() -> None:
    body = json.dumps(
        {
            "work_units": [{"id": "wu-1", "task": "task1 fixed", "sequence": 1}],
            "details": [],
        }
    )
    text = f"Here's the fix:\n```\n{body}\n```\n"
    payload = try_parse_tool_payload_from_text(text, "submit_fix")
    assert isinstance(payload, SubmitFixPayload)


def test_returns_none_for_empty_text() -> None:
    assert try_parse_tool_payload_from_text("", "submit_details") is None
    assert try_parse_tool_payload_from_text(None, "submit_details") is None  # type: ignore[arg-type]


def test_returns_none_for_unknown_tool() -> None:
    """Unknown tools fall through to the ValueError branch and are silently skipped."""
    body = json.dumps({"x": 1})
    assert try_parse_tool_payload_from_text(body, "submit_made_up_tool") is None


def test_returns_none_for_malformed_json() -> None:
    text = "Sure thing!\n```json\n{not valid json\n```\n"
    assert try_parse_tool_payload_from_text(text, "submit_details") is None


def test_returns_none_for_schema_mismatch() -> None:
    """JSON parses but doesn't match SubmitDetailsPayload schema (missing
    required ``details`` field). Caller falls back to abandon/escalate."""
    text = '```json\n{"wrong_field": "value"}\n```'
    assert try_parse_tool_payload_from_text(text, "submit_details") is None


# ---------------------------------------------------------------------------
# Tool-call envelope unwrapping
# ---------------------------------------------------------------------------
#
# Models that miss the MCP tool but write the call as JSON tend to wrap
# the arguments in a tool-call envelope (``{name, arguments}``) rather
# than emitting the bare payload. Without unwrapping, the validator sees
# only ``{name, arguments}`` and rejects the candidate.


def test_unwraps_anthropic_style_envelope() -> None:
    """``{"name": ..., "arguments": {...}}`` envelope unwraps to arguments."""
    from maverick.tools.agent_inbox.models import SubmitReviewPayload

    text = json.dumps(
        {
            "name": "submit_review",
            "arguments": {"approved": True, "findings": []},
        }
    )
    payload = try_parse_tool_payload_from_text(text, "submit_review")
    assert isinstance(payload, SubmitReviewPayload)
    assert payload.approved is True


def test_unwraps_envelope_in_fenced_block() -> None:
    """Same shape but inside ```json ... ``` fences (typical model output)."""
    from maverick.tools.agent_inbox.models import SubmitReviewPayload

    body = json.dumps(
        {
            "name": "submit_review",
            "arguments": {
                "approved": False,
                "findings": [
                    {"severity": "critical", "issue": "math is wrong"},
                ],
            },
        }
    )
    text = f"Here's the review:\n```json\n{body}\n```\n"
    payload = try_parse_tool_payload_from_text(text, "submit_review")
    assert isinstance(payload, SubmitReviewPayload)
    assert payload.approved is False
    assert len(payload.findings) == 1


def test_unwraps_tool_input_envelope() -> None:
    """``{"tool": ..., "input": {...}}`` envelope variant also unwraps."""
    from maverick.tools.agent_inbox.models import SubmitReviewPayload

    text = json.dumps(
        {
            "tool": "submit_review",
            "input": {"approved": True, "findings": []},
        }
    )
    payload = try_parse_tool_payload_from_text(text, "submit_review")
    assert isinstance(payload, SubmitReviewPayload)


def test_unwraps_single_key_envelope() -> None:
    """``{"submit_review": {...}}`` single-key wrap unwraps to the inner dict."""
    from maverick.tools.agent_inbox.models import SubmitReviewPayload

    text = json.dumps(
        {
            "submit_review": {"approved": True, "findings": []},
        }
    )
    payload = try_parse_tool_payload_from_text(text, "submit_review")
    assert isinstance(payload, SubmitReviewPayload)


def test_envelope_with_wrong_tool_name_is_not_unwrapped() -> None:
    """When ``name`` doesn't match the expected tool, validation runs on the
    outer dict (which won't match) and we return None."""
    text = json.dumps(
        {
            "name": "different_tool",
            "arguments": {"approved": True, "findings": []},
        }
    )
    assert try_parse_tool_payload_from_text(text, "submit_review") is None


def test_skips_invalid_candidate_continues_to_next() -> None:
    """First fenced block is invalid JSON; second is valid. We pick the second."""
    valid_body = json.dumps({"details": []})
    text = f"""First, garbage:
```json
{{not json
```

Second, valid:
```json
{valid_body}
```
"""
    payload = try_parse_tool_payload_from_text(text, "submit_details")
    assert isinstance(payload, SubmitDetailsPayload)


def test_skips_non_dict_json() -> None:
    """JSON that parses to a list / string / number isn't a tool payload."""
    text = "```json\n[1, 2, 3]\n```"
    assert try_parse_tool_payload_from_text(text, "submit_details") is None
