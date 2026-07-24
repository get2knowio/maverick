"""Tests for :class:`maverick.agents.spec_chain.SpecChainAgent`.

Uses a fake airframe runtime (same pattern as
``tests/unit/agents/test_generator_agent.py``) — no real adapter SDK is
touched.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.spec_chain import SpecChainAgent
from maverick.workflows.spec_chain.models import StepReport


def _report_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "artifacts": ["specs/001-foo/spec.md"],
        "questions": [],
        "findings": [],
        "detail": "Spec written from PRD.",
    }
    payload.update(overrides)
    return payload


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


def _make_runtime(
    structured: dict[str, Any],
    *,
    on_execute: Callable[[], None] | None = None,
) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"

    async def _execute(prompt: str, **kwargs: Any) -> RuntimeResult:
        if on_execute is not None:
            on_execute()
        return RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")

    runtime.execute = AsyncMock(side_effect=_execute)
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_run_step_returns_step_report(tmp_path: Path) -> None:
    runtime = _make_runtime(_report_payload())
    agent = SpecChainAgent(runtime=runtime, cwd=str(tmp_path))
    async with agent:
        report = await agent.run_step("/speckit.specify do the thing")
    assert isinstance(report, StepReport)
    assert report.status == "completed"
    assert report.artifacts == ["specs/001-foo/spec.md"]


async def test_run_step_uses_spec_chain_persona_and_schema(tmp_path: Path) -> None:
    runtime = _make_runtime(_report_payload())
    agent = SpecChainAgent(runtime=runtime, cwd=str(tmp_path))
    async with agent:
        await agent.run_step("prompt")
    call = runtime.execute.await_args
    assert call.kwargs["persona"] == "maverick.spec-chain"
    assert call.kwargs["schema"] is StepReport


async def test_run_step_binds_cwd_to_workspace_during_execute(tmp_path: Path) -> None:
    original_cwd = os.getcwd()
    observed: list[str] = []

    def _capture() -> None:
        observed.append(os.path.realpath(os.getcwd()))

    runtime = _make_runtime(_report_payload(), on_execute=_capture)
    agent = SpecChainAgent(runtime=runtime, cwd=str(tmp_path))
    async with agent:
        await agent.run_step("prompt")

    assert observed == [os.path.realpath(str(tmp_path))]
    assert os.getcwd() == original_cwd


async def test_run_step_restores_cwd_even_on_failure(tmp_path: Path) -> None:
    original_cwd = os.getcwd()
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(side_effect=RuntimeError("boom"))
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()

    agent = SpecChainAgent(runtime=runtime, cwd=str(tmp_path))
    async with agent:
        with pytest.raises(RuntimeError):
            await agent.run_step("prompt")

    assert os.getcwd() == original_cwd


async def test_close_routes_to_runtime(tmp_path: Path) -> None:
    runtime = _make_runtime(_report_payload())
    agent = SpecChainAgent(runtime=runtime, cwd=str(tmp_path))
    async with agent:
        pass
    runtime.close.assert_awaited_once()
