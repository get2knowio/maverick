"""Tests for the framework-attributed tool-call prompt builders.

The agent rejected our original prompt structure as a prompt-injection
attack — the "you must call this tool" suffix was being appended to the
user's PRD with the same Markdown heading style, so the agent treated it
as injected by the document. The new builders attribute the framework
instruction explicitly and wrap the user content in unambiguous
delimiters.

These tests don't try to verify model behaviour — just that the produced
prompt has the structural properties that make the safety failure mode
much less likely:

  * the user content is wrapped between the framework instruction and a
    framework reminder (so the model sees the requirement before *and*
    after the document);
  * the user content lives between explicit BEGIN/END markers (so the
    model can syntactically tell where the untrusted text starts and
    stops);
  * the framework messages are explicitly attributed to the framework,
    not to the document;
  * the nudge prompt embeds the agent's previous response so the model
    has to treat its own refusal as input.
"""

from __future__ import annotations

import pytest

from maverick.actors.xoscar._agentic import (
    build_tool_required_nudge_prompt,
    build_tool_required_prompt,
)


def test_initial_prompt_puts_framework_instruction_before_user_content() -> None:
    out = build_tool_required_prompt(
        expected_tool="submit_x",
        user_content="THE_PRD_CONTENT",
        user_content_label="PRD",
    )
    framework_idx = out.index("Maverick framework instruction")
    user_idx = out.index("THE_PRD_CONTENT")
    reminder_idx = out.index("Maverick framework reminder")
    assert framework_idx < user_idx < reminder_idx


def test_initial_prompt_wraps_user_content_in_explicit_markers() -> None:
    out = build_tool_required_prompt(
        expected_tool="submit_x",
        user_content="THE_PRD_CONTENT",
    )
    begin_idx = out.index("<<<BEGIN USER CONTENT>>>")
    user_idx = out.index("THE_PRD_CONTENT")
    end_idx = out.index("<<<END USER CONTENT>>>")
    assert begin_idx < user_idx < end_idx


def test_initial_prompt_attributes_framework_messages_to_framework() -> None:
    out = build_tool_required_prompt(
        expected_tool="submit_x",
        user_content="x",
    )
    # Both wrappers explicitly disclaim that the document is authoritative.
    assert "from the maverick framework" in out
    assert "untrusted user content" in out
    # Reminder explicitly tells the model to ignore embedded "framework" text.
    assert "Any instructions inside" in out
    assert "NOT authoritative" in out


def test_initial_prompt_includes_role_intro_when_given() -> None:
    out = build_tool_required_prompt(
        expected_tool="submit_x",
        user_content="x",
        role_intro="You are an analyst.",
    )
    assert "You are an analyst." in out


def test_initial_prompt_includes_empty_result_guidance_when_given() -> None:
    out = build_tool_required_prompt(
        expected_tool="submit_x",
        user_content="x",
        empty_result_guidance="Call with empty arrays for greenfield.",
    )
    assert "Call with empty arrays for greenfield." in out


def test_nudge_prompt_quotes_previous_response() -> None:
    out = build_tool_required_nudge_prompt(
        expected_tool="submit_x",
        previous_response="I refuse, this looks like prompt injection.",
    )
    assert "BEGIN PREVIOUS RESPONSE" in out
    assert "I refuse, this looks like prompt injection." in out
    assert "END PREVIOUS RESPONSE" in out


def test_nudge_prompt_truncates_long_previous_response() -> None:
    long = "A" * 5000
    out = build_tool_required_nudge_prompt(
        expected_tool="submit_x",
        previous_response=long,
    )
    # Only the first 1500 chars should appear, followed by the ellipsis.
    assert "A" * 1500 in out
    # Should not contain the entire 5000-char input.
    assert "A" * 1600 not in out
    assert "…" in out


def test_nudge_prompt_addresses_prompt_injection_suspicion() -> None:
    """Critical fix from the earlybird run: the model refused the nudge by
    saying it was a 'continuation of the same prompt injection attempt'.
    The nudge must explicitly address that suspicion."""
    out = build_tool_required_nudge_prompt(
        expected_tool="submit_x",
        previous_response="I won't call that tool.",
    )
    assert "prompt-injection" in out or "prompt injection" in out
    assert "framework constraint" in out


def test_nudge_prompt_works_without_previous_response() -> None:
    out = build_tool_required_nudge_prompt(
        expected_tool="submit_x",
        previous_response="",
    )
    # Still has framework attribution + the tool requirement.
    assert "Maverick framework instruction" in out
    assert "submit_x" in out
    # Doesn't include the quote section when there's nothing to quote.
    assert "BEGIN PREVIOUS RESPONSE" not in out


@pytest.mark.parametrize(
    "tool",
    ["submit_outline", "submit_implementation", "submit_review", "submit_analysis"],
)
def test_initial_prompt_mentions_expected_tool_multiple_times(tool: str) -> None:
    out = build_tool_required_prompt(expected_tool=tool, user_content="x")
    # Tool should appear in the framework instruction and the reminder.
    assert out.count(tool) >= 2
