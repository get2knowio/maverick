"""Tests for :class:`maverick.agents.decomposer.DecomposerAgent`."""

from __future__ import annotations

from typing import Any

from maverick.agents.decomposer import DecomposerAgent
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)

from .conftest import FakeClient, fake_handle, payload_send_result


class _DecomposerAgentForTest(DecomposerAgent):
    def __init__(self, *, client: FakeClient, **kwargs: Any) -> None:
        super().__init__(handle=fake_handle(), cwd="/tmp", **kwargs)
        self._fake_client = client

    def _build_client(self) -> Any:  # type: ignore[override]
        return self._fake_client


def _outline_payload() -> dict[str, Any]:
    return {
        "kind": "submit_outline",
        "work_units": [],
    }


def _details_payload() -> dict[str, Any]:
    return {
        "kind": "submit_details",
        "details": [],
    }


def _fix_payload() -> dict[str, Any]:
    return {
        "kind": "submit_fix",
        "work_units": [],
        "details": [],
    }


class _StubCodebaseContext:
    """Minimal duck-typed stand-in for CodebaseContext.

    The real ``build_outline_prompt`` calls ``_format_codebase_context``
    which iterates expected attributes. For tests that only exercise
    the agent's own logic (session rotation, payload return) we can
    replace the prompt builder via monkeypatch.
    """

    files: tuple[Any, ...] = ()


async def test_outline_returns_typed_payload(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_outline_prompt",
        lambda *args, **kwargs: "STUB OUTLINE PROMPT",
    )
    client = FakeClient(send_result=payload_send_result(_outline_payload()))
    agent = _DecomposerAgentForTest(client=client)
    async with agent:
        payload = await agent.outline(
            flight_plan_content="plan",
            codebase_context=_StubCodebaseContext(),
            briefing=None,
            runway_context=None,
        )
    assert isinstance(payload, SubmitOutlinePayload)
    # Outline mode resets the session counter to zero.
    assert agent._session_mode == "outline"  # noqa: SLF001
    # The outline mode opens a fresh session.
    assert client.created_sessions == ["decomposer.primary"]


async def test_detail_reuses_session_then_increments_turn_counter(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **kwargs: "DETAIL SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **kwargs: "DETAIL TURN",
    )
    client = FakeClient(send_result=payload_send_result(_details_payload()))
    agent = _DecomposerAgentForTest(client=client)
    await agent.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="vp",
    )
    async with agent:
        await agent.detail(unit_ids=["u-1"])
        sid_after_first = agent._session_id  # noqa: SLF001
        # Second detail call within the budget reuses the same session.
        await agent.detail(unit_ids=["u-2"])
        sid_after_second = agent._session_id  # noqa: SLF001
    assert sid_after_first == sid_after_second
    assert agent._session_mode == "detail"  # noqa: SLF001
    # Two turns recorded in detail mode.
    assert agent._session_turns_in_mode == 2  # noqa: SLF001


async def test_rotate_session_resets_mode_bookkeeping(monkeypatch: Any) -> None:
    """rotate_session() clears _session_mode + _session_turns_in_mode.

    Without this, ``squadron.rotate_for_new_bead()`` (which iterates
    :meth:`Agent.rotate_session` directly on every agent) would leave
    the decomposer carrying mode state from the previous unit's last
    phase — a footgun even if currently benign.
    """
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **kwargs: "SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **kwargs: "TURN",
    )
    client = FakeClient(send_result=payload_send_result(_details_payload()))
    agent = _DecomposerAgentForTest(client=client)
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


async def test_mode_switch_rotates_session(monkeypatch: Any) -> None:
    """Going outline → detail rotates the session."""
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_outline_prompt",
        lambda *args, **kwargs: "OUTLINE",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_seed_prompt",
        lambda **kwargs: "SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_detail_turn_prompt",
        lambda **kwargs: "TURN",
    )
    client = FakeClient(send_result=payload_send_result(_outline_payload()))
    agent = _DecomposerAgentForTest(client=client)
    await agent.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="",
    )
    async with agent:
        await agent.outline(
            flight_plan_content="x",
            codebase_context=_StubCodebaseContext(),
            briefing=None,
            runway_context=None,
        )
        first_sid = agent._session_id  # noqa: SLF001
        client.send_result = payload_send_result(_details_payload())
        await agent.detail(unit_ids=["u-1"])
        second_sid = agent._session_id  # noqa: SLF001
    assert first_sid != second_sid
    assert first_sid in client.deleted_sessions


async def test_fix_mode_reuses_seed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_fix_seed_prompt",
        lambda **kwargs: "FIX SEED",
    )
    monkeypatch.setattr(
        "maverick.library.actions.decompose.build_fix_turn_prompt",
        lambda **kwargs: "FIX TURN",
    )
    client = FakeClient(send_result=payload_send_result(_fix_payload()))
    agent = _DecomposerAgentForTest(client=client, fix_session_max_turns=3)
    async with agent:
        payload = await agent.fix(
            coverage_gaps=["g-1"],
            overloaded=[],
            outline_json='{"work_units": []}',
            details_json='{"details": []}',
            verification_properties="vp",
        )
    assert isinstance(payload, SubmitFixPayload)
    # First call seeded the context — subsequent calls within budget reuse it.
    assert agent._fix_seed_stale is False  # noqa: SLF001


async def test_nudge_picks_schema_for_expected_tool(monkeypatch: Any) -> None:
    client = FakeClient(send_result=payload_send_result(_details_payload()))
    agent = _DecomposerAgentForTest(client=client)
    async with agent:
        payload = await agent.nudge(
            expected_tool="submit_details", unit_id="u-1", reason="missing field"
        )
    assert isinstance(payload, SubmitDetailsPayload)
    sent_prompt = client.send_calls[0]["content"]
    assert "u-1" in sent_prompt
    assert "missing field" in sent_prompt
