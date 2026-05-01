"""Landmine 3: Claude wraps StructuredOutput payloads in envelopes ~30%
of the time. The unwrap helper must strip every observed shape.
"""

from __future__ import annotations

from maverick.runtime.opencode.client import (
    _unwrap_envelope,
    structured_of,
    structured_valid,
)


def _bare_message(structured: object) -> dict:
    return {
        "info": {"structured": structured, "providerID": "openrouter"},
        "parts": [
            {
                "type": "tool",
                "tool": "StructuredOutput",
                "state": {"input": structured, "metadata": {"valid": True}},
            }
        ],
    }


def test_unwrap_passthrough_for_bare_dict() -> None:
    payload = {"approved": True, "findings": []}
    assert _unwrap_envelope(payload) == payload


def test_unwrap_strips_input_envelope() -> None:
    bare = {"approved": True, "findings": []}
    enveloped = {"input": bare}
    assert _unwrap_envelope(enveloped) == bare


def test_unwrap_strips_parameter_envelope() -> None:
    bare = {"approved": False, "findings": [{"severity": "major", "issue": "x"}]}
    enveloped = {"parameter": bare}
    assert _unwrap_envelope(enveloped) == bare


def test_unwrap_strips_output_envelope() -> None:
    bare = {"approved": True, "findings": []}
    enveloped = {"output": bare}
    assert _unwrap_envelope(enveloped) == bare


def test_unwrap_decodes_content_string_envelope() -> None:
    bare = {"approved": True, "findings": []}
    enveloped = {"content": '{"approved": true, "findings": []}'}
    assert _unwrap_envelope(enveloped) == bare


def test_unwrap_leaves_content_string_alone_when_not_json() -> None:
    enveloped = {"content": "not json at all"}
    assert _unwrap_envelope(enveloped) == enveloped


def test_unwrap_does_not_strip_unknown_single_key() -> None:
    enveloped = {"approved": True}  # 'approved' is not an envelope key
    assert _unwrap_envelope(enveloped) == enveloped


def test_unwrap_does_not_strip_multi_key_dict() -> None:
    payload = {"input": "x", "extra": "y"}
    # Two keys means it is the actual payload — leave it alone.
    assert _unwrap_envelope(payload) == payload


def test_unwrap_handles_non_dict_input() -> None:
    assert _unwrap_envelope("string") == "string"
    assert _unwrap_envelope([1, 2, 3]) == [1, 2, 3]
    assert _unwrap_envelope(None) is None


def test_unwrap_recursive_for_nested_envelopes() -> None:
    bare = {"approved": True}
    enveloped = {"input": {"output": bare}}
    assert _unwrap_envelope(enveloped) == bare


def test_structured_of_unwraps_by_default() -> None:
    bare = {"approved": True, "findings": []}
    msg = _bare_message({"input": bare})
    assert structured_of(msg) == bare


def test_structured_of_can_skip_unwrap() -> None:
    enveloped = {"input": {"approved": True}}
    msg = _bare_message(enveloped)
    assert structured_of(msg, unwrap=False) == enveloped


def test_structured_of_falls_back_to_tool_state_when_no_info_field() -> None:
    bare = {"approved": True}
    msg = {
        "info": {},  # no 'structured' key
        "parts": [
            {
                "type": "tool",
                "tool": "StructuredOutput",
                "state": {"input": bare, "metadata": {"valid": True}},
            }
        ],
    }
    assert structured_of(msg) == bare


def test_structured_of_returns_none_when_no_payload() -> None:
    msg = {"info": {}, "parts": [{"type": "text", "text": "hi"}]}
    assert structured_of(msg) is None


def test_structured_valid_reads_metadata_flag() -> None:
    msg = _bare_message({"approved": True})
    assert structured_valid(msg) is True
    msg["parts"][0]["state"]["metadata"]["valid"] = False
    assert structured_valid(msg) is False


def test_structured_valid_false_when_no_tool_part() -> None:
    msg = {"info": {}, "parts": [{"type": "text", "text": "hi"}]}
    assert structured_valid(msg) is False
