"""Tests for :class:`maverick.agents.decomposer.DecomposerAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.decomposer import DecomposerAgent
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)


def _outline_payload() -> dict[str, Any]:
    return {"kind": "submit_outline", "work_units": []}


def _details_payload() -> dict[str, Any]:
    return {"kind": "submit_details", "details": []}


def _fix_payload() -> dict[str, Any]:
    return {"kind": "submit_fix", "work_units": [], "details": []}


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.02,
        input_tokens=20,
        output_tokens=40,
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


class _StubCodebaseContext:
    files: tuple[Any, ...] = ()


async def test_outline_returns_typed_payload(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_outline_prompt",
        lambda *a, **k: "stubbed outline",
    )
    runtime = _make_runtime(_outline_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.outline(
            flight_plan_content="plan",
            codebase_context=_StubCodebaseContext(),
        )
    assert isinstance(payload, SubmitOutlinePayload)
    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitOutlinePayload
    assert call.kwargs["persona"] == "maverick.decomposer"
    assert agent._session_mode == "outline"  # noqa: SLF001


async def test_detail_reuses_session_then_increments_turn_counter(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **kwargs: "DETAIL SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **kwargs: "DETAIL TURN",
    )
    runtime = _make_runtime(_details_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    await agent.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="vp",
    )
    async with agent:
        await agent.detail(unit_ids=["u-1"])
        await agent.detail(unit_ids=["u-2"])
    assert agent._session_mode == "detail"  # noqa: SLF001
    # Two turns recorded in detail mode; runtime.reset was not called between them.
    assert agent._session_turns_in_mode == 2  # noqa: SLF001
    runtime.reset.assert_not_called()


async def test_rotate_session_resets_mode_bookkeeping(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **kwargs: "SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **kwargs: "TURN",
    )
    runtime = _make_runtime(_details_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    await agent.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="vp",
    )
    async with agent:
        await agent.detail(unit_ids=["u-1"])
        assert agent._session_mode == "detail"  # noqa: SLF001
        assert agent._session_turns_in_mode == 1  # noqa: SLF001

        await agent.rotate_session()

        assert agent._session_mode is None  # noqa: SLF001
        assert agent._session_turns_in_mode == 0  # noqa: SLF001
    runtime.reset.assert_awaited()


async def test_mode_switch_rotates_session(monkeypatch: Any) -> None:
    """outline → detail rotates the runtime."""
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_outline_prompt",
        lambda *a, **k: "OUTLINE",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **k: "SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **k: "TURN",
    )
    runtime = _make_runtime(_outline_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    await agent.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="",
    )
    async with agent:
        await agent.outline(
            flight_plan_content="x",
            codebase_context=_StubCodebaseContext(),
        )
        # Swap return to details for second call.
        runtime.execute.return_value = RuntimeResult(
            text="", structured=_details_payload(), cost=_cost(), finish="end_turn"
        )
        await agent.detail(unit_ids=["u-1"])
    runtime.reset.assert_awaited()
    assert agent._session_mode == "detail"  # noqa: SLF001


async def test_fix_mode_reuses_seed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_fix_seed_prompt",
        lambda **kwargs: "FIX SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_fix_turn_prompt",
        lambda **kwargs: "FIX TURN",
    )
    runtime = _make_runtime(_fix_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp", fix_session_max_turns=3)
    async with agent:
        payload = await agent.fix(
            coverage_gaps=["g-1"],
            overloaded=[],
            outline_json='{"work_units": []}',
            details_json='{"details": []}',
            verification_properties="vp",
        )
    assert isinstance(payload, SubmitFixPayload)
    assert agent._fix_seed_stale is False  # noqa: SLF001


async def test_nudge_picks_schema_for_expected_tool() -> None:
    runtime = _make_runtime(_details_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.nudge(
            expected_tool="submit_details", unit_id="u-1", reason="missing field"
        )
    assert isinstance(payload, SubmitDetailsPayload)
    sent_prompt = runtime.execute.await_args.args[0]
    assert "u-1" in sent_prompt
    assert "missing field" in sent_prompt


async def test_detail_rotates_session_on_mode_change_from_outline() -> None:
    runtime = _make_runtime(_details_payload())
    agent = DecomposerAgent(runtime=runtime, cwd="/tmp")
    agent._session_mode = "outline"  # noqa: SLF001
    agent._session_turns_in_mode = 1  # noqa: SLF001

    async with agent:
        with patch.object(agent, "_build_detail_prompt", return_value=("detail prompt", True)):
            await agent.detail(unit_ids=["u-1"])

    runtime.reset.assert_awaited()
    assert agent._session_mode == "detail"  # noqa: SLF001
