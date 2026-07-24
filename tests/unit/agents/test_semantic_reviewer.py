"""Tests for :class:`maverick.agents.semantic_reviewer.SemanticDependentsAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.semantic_reviewer import SemanticDependentsAgent
from maverick.payloads import SubmitSemanticDependentsPayload


def _findings_payload(*change_ids: str, dependent: bool = False) -> dict[str, Any]:
    return {
        "kind": "submit_semantic_dependents",
        "findings": [
            {
                "change_id": change_id,
                "dependent": dependent,
                "reason": "traces to old assumption" if dependent else "",
                "fix_instructions": "do the fix" if dependent else "",
            }
            for change_id in change_ids
        ],
    }


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


def _make_runtime(structured: dict[str, Any]) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_analyze_returns_validated_payload() -> None:
    runtime = _make_runtime(_findings_payload("abc123"))
    agent = SemanticDependentsAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.analyze(
            question="Should we use UUIDs?",
            adopted_answer="Yes, use UUIDs everywhere.",
            human_answer="No, use sequential integers.",
            correction_diff="- uuid_field\n+ int_field",
            descendants=[("abc123", "+ some_dependent_code")],
        )
    assert isinstance(payload, SubmitSemanticDependentsPayload)
    assert payload.findings[0].change_id == "abc123"

    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitSemanticDependentsPayload


async def test_analyze_class_attrs() -> None:
    assert SemanticDependentsAgent.provider_tier == "review"
    assert SemanticDependentsAgent.persona_name == "maverick.semantic-reviewer"
    assert SemanticDependentsAgent.result_model is SubmitSemanticDependentsPayload


async def test_analyze_prompt_contains_context_verbatim() -> None:
    runtime = _make_runtime(_findings_payload("c1"))
    agent = SemanticDependentsAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.analyze(
            question="UNIQUE-QUESTION-TEXT",
            adopted_answer="UNIQUE-ADOPTED-ANSWER-TEXT",
            human_answer="UNIQUE-HUMAN-ANSWER-TEXT",
            correction_diff="UNIQUE-CORRECTION-DIFF-TEXT",
            descendants=[("c1", "UNIQUE-DESCENDANT-DIFF-TEXT")],
        )
    prompt = runtime.execute.await_args.args[0]
    assert "UNIQUE-QUESTION-TEXT" in prompt
    assert "UNIQUE-ADOPTED-ANSWER-TEXT" in prompt
    assert "UNIQUE-HUMAN-ANSWER-TEXT" in prompt
    assert "UNIQUE-CORRECTION-DIFF-TEXT" in prompt


async def test_analyze_prompt_contains_single_descendant() -> None:
    runtime = _make_runtime(_findings_payload("change-1"))
    agent = SemanticDependentsAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.analyze(
            question="q",
            adopted_answer="a",
            human_answer="h",
            correction_diff="cd",
            descendants=[("change-1", "DESCENDANT-DIFF-ONE")],
        )
    prompt = runtime.execute.await_args.args[0]
    assert "change-1" in prompt
    assert "DESCENDANT-DIFF-ONE" in prompt


async def test_analyze_prompt_contains_multiple_descendants() -> None:
    runtime = _make_runtime(_findings_payload("change-1", "change-2", "change-3"))
    agent = SemanticDependentsAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.analyze(
            question="q",
            adopted_answer="a",
            human_answer="h",
            correction_diff="cd",
            descendants=[
                ("change-1", "DESCENDANT-DIFF-ONE"),
                ("change-2", "DESCENDANT-DIFF-TWO"),
                ("change-3", "DESCENDANT-DIFF-THREE"),
            ],
        )
    prompt = runtime.execute.await_args.args[0]
    for change_id, diff_text in (
        ("change-1", "DESCENDANT-DIFF-ONE"),
        ("change-2", "DESCENDANT-DIFF-TWO"),
        ("change-3", "DESCENDANT-DIFF-THREE"),
    ):
        assert change_id in prompt
        assert diff_text in prompt
    assert len(payload.findings) == 3


async def test_analyze_prompt_lists_expected_change_ids() -> None:
    runtime = _make_runtime(_findings_payload("change-1", "change-2"))
    agent = SemanticDependentsAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.analyze(
            question="q",
            adopted_answer="a",
            human_answer="h",
            correction_diff="cd",
            descendants=[
                ("change-1", "diff-one"),
                ("change-2", "diff-two"),
            ],
        )
    prompt = runtime.execute.await_args.args[0]
    # Expected ids should be explicitly enumerated somewhere in the prompt
    # (not just embedded in per-descendant section headers) so the model
    # can't invent or omit ids.
    assert prompt.count("change-1") >= 2
    assert prompt.count("change-2") >= 2


def test_construction_requires_cwd() -> None:
    with pytest.raises(ValueError, match="requires 'cwd'"):
        SemanticDependentsAgent(runtime=MagicMock(), cwd="")
