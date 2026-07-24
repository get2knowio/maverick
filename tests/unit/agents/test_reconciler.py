"""Tests for :class:`maverick.agents.reconciler.ReconcilerAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.reconciler import ReconcilerAgent
from maverick.payloads import SubmitConflictResolutionPayload, SubmitCorrectionPayload


def _correction_payload() -> dict[str, Any]:
    return {
        "kind": "submit_correction",
        "summary": "updated the retry limit to match the new answer",
        "files_touched": ["src/thing.py"],
        "no_change_required": False,
    }


def _conflict_resolution_payload() -> dict[str, Any]:
    return {
        "kind": "submit_conflict_resolution",
        "resolved_files": ["src/thing.py"],
        "unresolvable": [],
        "notes": "resolved in favor of the new answer",
    }


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.05,
        input_tokens=50,
        output_tokens=100,
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


def test_persona_and_tier_class_attrs() -> None:
    assert ReconcilerAgent.persona_name == "maverick.reconciler"
    assert ReconcilerAgent.provider_tier == "implement"
    assert ReconcilerAgent.result_model is SubmitCorrectionPayload


async def test_correct_returns_typed_payload() -> None:
    runtime = _make_runtime(_correction_payload())
    agent = ReconcilerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.correct(
            question="Should retries be capped at 3?",
            adopted_answer="No cap, retry forever.",
            human_answer="Cap retries at 3.",
            target_diff="diff --git a/src/thing.py b/src/thing.py\n+retries = None",
        )
    assert isinstance(payload, SubmitCorrectionPayload)
    assert payload.summary == "updated the retry limit to match the new answer"

    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitCorrectionPayload
    assert call.kwargs["persona"] == "maverick.reconciler"

    prompt = call.args[0]
    assert "Should retries be capped at 3?" in prompt
    assert "No cap, retry forever." in prompt
    assert "Cap retries at 3." in prompt
    assert "diff --git a/src/thing.py b/src/thing.py" in prompt
    assert "+retries = None" in prompt


async def test_resolve_conflicts_returns_typed_payload() -> None:
    runtime = _make_runtime(_conflict_resolution_payload())
    agent = ReconcilerAgent(runtime=runtime, cwd="/tmp")
    conflicted_files = {
        "src/thing.py": "<<<<<<< left\nretries = None\n=======\nretries = 3\n>>>>>>> right",
        "src/other.py": "<<<<<<< left\ncap = False\n=======\ncap = True\n>>>>>>> right",
    }
    async with agent:
        payload = await agent.resolve_conflicts(
            question="Should retries be capped at 3?",
            adopted_answer="No cap, retry forever.",
            human_answer="Cap retries at 3.",
            conflicted_files=conflicted_files,
        )
    assert isinstance(payload, SubmitConflictResolutionPayload)
    assert payload.resolved_files == ("src/thing.py",)

    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitConflictResolutionPayload
    assert call.kwargs["persona"] == "maverick.reconciler"

    prompt = call.args[0]
    assert "Should retries be capped at 3?" in prompt
    assert "No cap, retry forever." in prompt
    assert "Cap retries at 3." in prompt
    for path, content in conflicted_files.items():
        assert path in prompt
        assert content in prompt


async def test_correct_and_resolve_conflicts_share_runtime_session() -> None:
    """No rotate_session() call between the two methods within one answer."""
    runtime = _make_runtime(_correction_payload())
    agent = ReconcilerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.correct(
            question="q",
            adopted_answer="old",
            human_answer="new",
            target_diff="diff",
        )
        runtime.execute.return_value = RuntimeResult(
            text="", structured=_conflict_resolution_payload(), cost=_cost(), finish="end_turn"
        )
        await agent.resolve_conflicts(
            question="q",
            adopted_answer="old",
            human_answer="new",
            conflicted_files={"a.py": "content"},
        )
    runtime.reset.assert_not_awaited()


async def test_rotate_session_resets_runtime() -> None:
    runtime = _make_runtime(_correction_payload())
    agent = ReconcilerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.correct(
            question="q",
            adopted_answer="old",
            human_answer="new",
            target_diff="diff",
        )
        await agent.rotate_session()
    runtime.reset.assert_awaited()


async def test_close_calls_runtime_close() -> None:
    runtime = _make_runtime(_correction_payload())
    agent = ReconcilerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        pass
    runtime.close.assert_awaited_once()


def test_construction_requires_cwd() -> None:
    with pytest.raises(ValueError, match="requires 'cwd'"):
        ReconcilerAgent(runtime=MagicMock(), cwd="")
