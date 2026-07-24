"""Integration tests for halt semantics (US3, T027).

A failed clarify halts the chain before plan/tasks/analyze ever run
(FR-008/FR-009); a mid-chain plan failure halts the same way; an analyze
failure degrades to a warning and the chain still completes (FR-012).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow
from tests.integration.spec_chain.conftest import (
    FEATURE,
    FEATURE_DIR,
    make_config,
    stub_runtime_factory,
)


def _blocked_handler(feature_path: Path, runtime: Any) -> dict[str, Any]:
    return {
        "status": "blocked",
        "artifacts": [],
        "questions": [],
        "findings": [],
        "detail": "Cannot form a defensible default for a critical question.",
    }


def _failing_no_artifacts_handler(feature_path: Path, runtime: Any) -> dict[str, Any]:
    """Reports success but writes nothing — filesystem is ground truth (R9),
    so this must still be treated as a failure."""
    return {
        "status": "completed",
        "artifacts": [],
        "questions": [],
        "findings": [],
        "detail": "Claims success but wrote nothing.",
    }


async def _run_workflow(
    speckit_repo: Path, fake_home: Path, *, run_id: str = "test-halt"
) -> tuple[Any, list]:
    workflow = SpecChainWorkflow(config=make_config())
    inputs = {
        "run_id": run_id,
        "feature": FEATURE,
        "cwd": str(speckit_repo),
        "prd_path": str(speckit_repo / "docs" / "prd.md"),
        "home": str(fake_home),
    }
    events = [event async for event in workflow.execute(inputs)]
    return workflow, events


class TestClarifyFailureHalts:
    async def test_clarify_blocked_halts_before_plan(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.CLARIFY: _blocked_handler})
        workflow, events = await _run_workflow(speckit_repo, fake_home, run_id="test-clarify-halt")

        assert workflow.result is not None
        # _run() doesn't raise on a domain halt — it's a reported failure,
        # not a crash (base.py distinguishes the two).
        assert workflow.result.success is True

        state = await load_chain_state("test-clarify-halt", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.SPECIFY].status == "succeeded"
        assert state.steps[ChainStep.CLARIFY].status == "failed"
        assert state.steps[ChainStep.PLAN].status == "skipped"
        assert state.steps[ChainStep.TASKS].status == "skipped"
        assert state.steps[ChainStep.ANALYZE].status == "skipped"

        # plan.md/tasks.md never landed in the checkout.
        feature_path = speckit_repo / "specs" / FEATURE_DIR
        assert (feature_path / "spec.md").is_file()
        assert not (feature_path / "plan.md").exists()
        assert not (feature_path / "tasks.md").exists()

        report = workflow.result.final_output
        assert report["status"] == "halted"
        assert report["resume_hint"] == f"maverick spec {FEATURE}"

    async def test_clarify_no_artifacts_halts(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        """Clarify claims success but the filesystem shows no spec.md
        left behind — R9: filesystem wins over the agent's claim."""

        def _clarify_deletes_spec(feature_path: Path, runtime: Any) -> dict[str, Any]:
            spec_path = feature_path / "spec.md"
            if spec_path.is_file():
                spec_path.unlink()
            return {
                "status": "completed",
                "artifacts": [],
                "questions": [],
                "findings": [],
                "detail": "oops",
            }

        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.CLARIFY: _clarify_deletes_spec})
        workflow, _ = await _run_workflow(speckit_repo, fake_home, run_id="test-clarify-no-art")

        state = await load_chain_state("test-clarify-no-art", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.CLARIFY].status == "failed"


class TestMidChainStepFailureHalts:
    async def test_plan_failure_halts_before_tasks_and_analyze(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.PLAN: _failing_no_artifacts_handler}
        )
        workflow, _ = await _run_workflow(speckit_repo, fake_home, run_id="test-plan-halt")

        state = await load_chain_state("test-plan-halt", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.SPECIFY].status == "succeeded"
        assert state.steps[ChainStep.CLARIFY].status == "succeeded"
        assert state.steps[ChainStep.PLAN].status == "failed"
        assert state.steps[ChainStep.TASKS].status == "skipped"
        assert state.steps[ChainStep.ANALYZE].status == "skipped"

        feature_path = speckit_repo / "specs" / FEATURE_DIR
        assert (feature_path / "spec.md").is_file()
        assert not (feature_path / "tasks.md").exists()

        report = workflow.result.final_output
        assert report["status"] == "halted"


class TestAnalyzeFailureIsAWarningNotAHalt:
    async def test_analyze_failure_degrades_to_warning_chain_still_completes(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.ANALYZE: _failing_no_artifacts_handler}
        )
        # (analyze's handler "failing" here just needs status != completed
        # with no verifiable artifacts to trigger `_fail_step`; since
        # analyze requires zero artifacts, force a genuine failure via a
        # status="failed" report instead.)

        def _analyze_fails(feature_path: Path, runtime: Any) -> dict[str, Any]:
            return {
                "status": "failed",
                "artifacts": [],
                "questions": [],
                "findings": [],
                "detail": "analyze crashed",
            }

        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.ANALYZE: _analyze_fails})
        workflow, events = await _run_workflow(speckit_repo, fake_home, run_id="test-analyze-warn")

        # The step record itself does show "failed" (it genuinely failed —
        # the agent self-reported it and the workflow trusts that per
        # FR-009's honest-blocked/failed-report handling); FR-012 is about
        # the *chain*, not the step record: the chain still completes
        # (status="completed") rather than halting.
        state = await load_chain_state("test-analyze-warn", speckit_repo)
        assert state is not None
        assert state.status == "completed"
        assert state.steps[ChainStep.ANALYZE].status == "failed"

        report = workflow.result.final_output
        assert report["status"] == "completed"

    async def test_analyze_runtime_exception_is_warning_not_halt(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        """A genuine analyze-step runtime failure (e.g. every retry attempt
        raises) still degrades to a warning — FR-012 — rather than halting
        the otherwise-successful chain."""

        def _analyze_raises(feature_path: Path, runtime: Any) -> dict[str, Any]:
            raise RuntimeError("analyze runtime crashed")

        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.ANALYZE: _analyze_raises})
        workflow, events = await _run_workflow(
            speckit_repo, fake_home, run_id="test-analyze-crash"
        )

        state = await load_chain_state("test-analyze-crash", speckit_repo)
        assert state is not None
        assert state.status == "completed"
        assert state.steps[ChainStep.ANALYZE].status == "failed"

        warning_events = [
            e
            for e in events
            if type(e).__name__ == "StepOutput" and getattr(e, "level", None) == "warning"
        ]
        assert any("analyze failed" in e.message for e in warning_events)

        report = workflow.result.final_output
        assert report["status"] == "completed"
        assert report["resume_hint"] is None
