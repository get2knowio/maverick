"""Tests for xoscar plan-generation actors.

Covers the plan-specific deterministic actors (PlanValidator, PlanWriter),
the GeneratorActor's inbox dispatch, and PlanSupervisor construction +
typed domain methods.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.generator import GeneratorActor
from maverick.actors.xoscar.messages import (
    PlanValidateRequest,
    PromptError,
    WritePlanRequest,
)
from maverick.actors.xoscar.plan_supervisor import PlanInputs, PlanSupervisor
from maverick.actors.xoscar.plan_validator import PlanValidatorActor
from maverick.actors.xoscar.plan_writer import PlanWriterActor
from maverick.payloads import (
    SubmitFlightPlanPayload,
)

# ---------------------------------------------------------------------------
# Plan deterministic actors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_writer_writes_both_files(pool_address: str, tmp_path: Path) -> None:
    output_dir = tmp_path / "plan-out"
    ref = await xo.create_actor(
        PlanWriterActor,
        output_dir=str(output_dir),
        address=pool_address,
        uid="plan-writer",
    )
    try:
        result = await ref.write(
            WritePlanRequest(
                flight_plan_markdown="# Flight Plan\n\n...",
                briefing_markdown="# Briefing\n\n...",
            )
        )
        assert Path(result.flight_plan_path).exists()
        assert result.briefing_path is not None
        assert Path(result.briefing_path).exists()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_plan_writer_skips_briefing_when_empty(pool_address: str, tmp_path: Path) -> None:
    output_dir = tmp_path / "plan-out"
    ref = await xo.create_actor(
        PlanWriterActor,
        output_dir=str(output_dir),
        address=pool_address,
        uid="plan-writer-nobrief",
    )
    try:
        result = await ref.write(WritePlanRequest(flight_plan_markdown="# plan"))
        assert Path(result.flight_plan_path).exists()
        assert result.briefing_path is None
    finally:
        await xo.destroy_actor(ref)


def test_plan_writer_requires_output_dir() -> None:
    with pytest.raises(ValueError, match="output_dir"):
        PlanWriterActor(output_dir="")


@pytest.mark.asyncio
async def test_plan_validator_returns_warnings(pool_address: str, tmp_path: Path) -> None:
    ref = await xo.create_actor(
        PlanValidatorActor,
        address=pool_address,
        uid="plan-validator",
    )
    try:
        fp = {
            "objective": "test",
            "success_criteria": [{"description": "SC1", "verification": "echo ok"}],
            "in_scope": ["x"],
            "out_of_scope": [],
            "boundaries": [],
            "constraints": [],
            "context": "",
            "notes": "",
            "tags": [],
            "name": "test-plan",
            "version": "1",
        }
        result = await ref.validate(
            PlanValidateRequest(
                flight_plan=fp,
                plan_name="test-plan",
                prd_content="build a thing",
            )
        )
        assert isinstance(result.warnings, tuple)
    finally:
        await xo.destroy_actor(ref)


# ---------------------------------------------------------------------------
# Generator inbox dispatch
# ---------------------------------------------------------------------------


class _PlanRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    async def flight_plan_ready(self, payload: SubmitFlightPlanPayload) -> None:
        self._calls.append(("flight_plan_ready", payload))

    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    async def prompt_error(self, error: Any) -> None:
        self._calls.append(("prompt_error", error))

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


class _StubGenerator(GeneratorActor):
    """GeneratorActor with the OpenCode client replaced by a stub."""

    # Bypass the tier cascade — stub doesn't surface real /provider data.
    provider_tier = None  # type: ignore[assignment]

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str = "/tmp",
        scripted_payload: dict | None = None,
        scripted_error: BaseException | None = None,
    ) -> None:
        super().__init__(supervisor_ref, cwd=cwd)
        self._scripted_payload = scripted_payload
        self._scripted_error = scripted_error

    async def _build_client(self) -> Any:  # type: ignore[override]
        from maverick.runtime.opencode import SendResult

        scripted_payload = self._scripted_payload
        scripted_error = self._scripted_error

        class _Client:
            base_url = "http://stub"

            async def list_providers(self) -> dict[str, Any]:
                return {"all": [], "connected": []}

            async def create_session(self, *, title: str | None = None, **_: Any) -> str:
                return "ses_1"

            async def delete_session(self, session_id: str) -> bool:
                return True

            async def send_with_event_watch(self, *args: Any, **kwargs: Any) -> SendResult:
                if scripted_error is not None:
                    raise scripted_error
                payload = scripted_payload
                return SendResult(
                    message={"info": {"structured": payload}, "parts": []},
                    text="",
                    structured=payload,
                    valid=True,
                    info={},
                )

            async def aclose(self) -> None:
                return None

        return _Client()


@pytest.mark.asyncio
async def test_generator_forwards_flight_plan(pool_address: str) -> None:
    sup = await xo.create_actor(_PlanRecorder, address=pool_address, uid="gen-sup")
    payload = {
        "objective": "Ship feature X",
        "success_criteria": [{"description": "SC1", "verification": "echo ok"}],
        "in_scope": ["a"],
        "out_of_scope": [],
        "context": "",
        "tags": [],
    }
    gen = await xo.create_actor(
        _StubGenerator,
        sup,
        cwd="/tmp",
        scripted_payload=payload,
        address=pool_address,
        uid="gen-1",
    )
    try:
        from maverick.actors.xoscar.messages import GenerateRequest

        await gen.send_generate(GenerateRequest(prompt="prd"))
        calls = await sup.calls()
        assert len(calls) == 1
        kind, delivered = calls[0]
        assert kind == "flight_plan_ready"
        assert isinstance(delivered, SubmitFlightPlanPayload)
        assert delivered.objective == "Ship feature X"
    finally:
        await xo.destroy_actor(gen)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_generator_routes_send_error_to_prompt_error(pool_address: str) -> None:
    from maverick.runtime.opencode import OpenCodeAuthError

    sup = await xo.create_actor(_PlanRecorder, address=pool_address, uid="gen-sup-err")
    gen = await xo.create_actor(
        _StubGenerator,
        sup,
        cwd="/tmp",
        scripted_error=OpenCodeAuthError("bad key"),
        address=pool_address,
        uid="gen-err",
    )
    try:
        from maverick.actors.xoscar.messages import GenerateRequest

        await gen.send_generate(GenerateRequest(prompt="x"))
        calls = await sup.calls()
        kinds = [k for k, _ in calls]
        assert "prompt_error" in kinds
        # The supervisor recorder stores PromptError dataclasses; pull
        # the first one off and assert its phase.
        prompt_err = next(detail for k, detail in calls if k == "prompt_error")
        assert prompt_err.phase == "generate"
    finally:
        await xo.destroy_actor(gen)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# PlanSupervisor smoke tests
# ---------------------------------------------------------------------------


def test_plan_inputs_require_fields(tmp_path: Path) -> None:
    for bad in (
        {"cwd": "", "plan_name": "x", "output_dir": str(tmp_path)},
        {"cwd": "/tmp", "plan_name": "", "output_dir": str(tmp_path)},
        {"cwd": "/tmp", "plan_name": "x", "output_dir": ""},
    ):
        with pytest.raises(ValueError):
            PlanSupervisor(PlanInputs(prd_content="p", **bad))


@pytest.mark.asyncio
async def test_plan_supervisor_construction_creates_children(
    pool_address: str, tmp_path: Path
) -> None:
    sup = await xo.create_actor(
        PlanSupervisor,
        PlanInputs(
            cwd="/tmp",
            plan_name="test-plan",
            prd_content="prd text",
            output_dir=str(tmp_path / "out"),
        ),
        address=pool_address,
        uid="plan-sup-construct",
    )
    try:
        pass  # __post_create__ would have raised if any child failed.
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_plan_prompt_error_marks_done(pool_address: str, tmp_path: Path) -> None:
    sup = await xo.create_actor(
        PlanSupervisor,
        PlanInputs(
            cwd="/tmp",
            plan_name="test-plan",
            prd_content="prd",
            output_dir=str(tmp_path / "out"),
        ),
        address=pool_address,
        uid="plan-sup-error",
    )
    try:
        await sup.prompt_error(PromptError(phase="generate", error="ACP died"))
        result = await sup.get_terminal_result()
        assert result is not None
        assert result["success"] is False
        assert "ACP died" in result["error"]
    finally:
        await xo.destroy_actor(sup)
